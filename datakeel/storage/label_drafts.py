# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Execute an approved draft: read its sources, draft, and store an unpublished version."""

import base64
import io
import re
from collections import defaultdict

import httpx
from PIL import Image, UnidentifiedImageError
from sqlalchemy import select
from sqlalchemy.orm import Session

from datakeel.actions.label_draft_parameters import DraftLabelSetParams
from datakeel.actions.models import ActionPlan, OperationResult
from datakeel.actions.production_catalog_parameters import CreateLabelSetParams
from datakeel.core.annotation_models import AnnotationBatch
from datakeel.core.errors import ValidationError
from datakeel.core.label_guidelines import DraftSource
from datakeel.core.models import AssetRef, FileItem, utcnow
from datakeel.core.production_catalog_models import LabelSet
from datakeel.core.settings import get_settings
from datakeel.core.standard_models import CodeList, FieldStandard
from datakeel.label_drafts.model import model_draft
from datakeel.label_drafts.models import (
    AttributeSource,
    CategorySource,
    DraftInputs,
    DraftOutcome,
    SampleSource,
)
from datakeel.label_drafts.offline import offline_draft
from datakeel.storage.action_selection import selected_files
from datakeel.storage.annotation_rows import AnnotationBatchRow
from datakeel.storage.objects import object_store
from datakeel.storage.production_catalog import annotation_categories, label_set_row
from datakeel.storage.production_catalog_changes import create_label_set
from datakeel.storage.production_catalog_rows import ProductionLabelSetRow
from datakeel.storage.standard_store import state_in_session

IMAGE_EDGE = 768
CATEGORY_WORDS = re.compile(r"类型|类别|种类|分类|type|class|category|kind", re.IGNORECASE)
BATCH_LIMIT = 20


def _standard_sources(
    session: Session, codes: tuple[str, ...]
) -> tuple[list[CategorySource], list[AttributeSource]]:
    contract = state_in_session(session).contract
    fields = {item.code: item for item in contract.standards}
    lists = {item.code: item for item in contract.code_lists}
    categories: list[CategorySource] = []
    attributes: list[AttributeSource] = []
    for code in _category_first(codes, fields, lists):
        field = fields.get(code)
        listing = lists.get(field.code_list or "") if field else lists.get(code)
        if field is None and listing is None:
            message = f"Unknown data standard code: {code}"
            raise ValidationError(message)
        options = (
            tuple((str(e.value), e.label_zh, e.label_en) for e in listing.entries)
            if listing
            else ()
        )
        if listing is not None and not categories:
            root = field.code if field else listing.code
            categories.append(
                CategorySource(
                    key=root,
                    name_zh=field.name_zh if field else listing.name,
                    name_en=field.name_en if field else "",
                    description=field.description if field else "",
                )
            )
            categories += [
                CategorySource(key=f"{root}.{value}", name_zh=zh, name_en=en, parent_key=root)
                for value, zh, en in options
            ]
        elif field is not None:
            attributes.append(
                AttributeSource(
                    key=field.code,
                    name_zh=field.name_zh,
                    name_en=field.name_en,
                    data_type=field.data_type,
                    options=options,
                    required=field.required,
                )
            )
    return categories, attributes


def _category_first(
    codes: tuple[str, ...], fields: dict[str, FieldStandard], lists: dict[str, CodeList]
) -> list[str]:
    """The category tree comes from the code list that names a kind or class, else the largest."""

    def rank(code: str) -> tuple[bool, int]:
        field = fields.get(code)
        listing = lists.get(field.code_list or "") if field else lists.get(code)
        names = f"{code} {field.name_zh if field else ''} {field.name_en if field else ''}"
        named = bool(CATEGORY_WORDS.search(names))
        return (not named, -(len(listing.entries) if listing else -1))

    return sorted(codes, key=rank)


def _label_set_sources(session: Session, identifiers: tuple[str, ...]) -> list[CategorySource]:
    found: list[CategorySource] = []
    for identifier in identifiers:
        versions = session.scalars(
            select(ProductionLabelSetRow.version).where(
                ProductionLabelSetRow.label_set_id == identifier
            )
        ).all()
        if not versions:
            message = f"Label set was not found: {identifier}"
            raise ValidationError(message)
        labels = LabelSet.model_validate(label_set_row(session, identifier, max(versions)).payload)
        found += [
            CategorySource(
                key=label.id,
                name_zh=label.name_zh or label.name,
                name_en=label.name_en or "",
                parent_key=label.parent_id,
                origin="annotation",
            )
            for label in labels.labels
        ]
    return found


def _annotated(session: Session, datasets: tuple[str, ...]) -> dict[str, set[str]]:
    labels: dict[str, set[str]] = defaultdict(set)
    if not datasets:
        return labels
    rows = session.scalars(
        select(AnnotationBatchRow)
        .where(AnnotationBatchRow.dataset_id.in_(datasets))
        .order_by(AnnotationBatchRow.created_at.desc())
        .limit(BATCH_LIMIT)
    )
    for row in rows:
        for record in AnnotationBatch.model_validate(row.batch).annotations:
            labels[record.sample_id].update(annotation_categories(record))
    return labels


def _image(file: FileItem) -> str | None:
    key = file.metadata.get("object_key")
    if file.modality != "image" or not isinstance(key, str):
        return None
    try:
        with Image.open(object_store().materialize(key)) as image:
            image.thumbnail((IMAGE_EDGE, IMAGE_EDGE))
            buffer = io.BytesIO()
            image.convert("RGB").save(buffer, format="JPEG", quality=85)
    except (OSError, UnidentifiedImageError, ValueError):
        return None
    return "data:image/jpeg;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


def _text(file: FileItem) -> str:
    key = file.metadata.get("object_key")
    if file.modality != "text" or not isinstance(key, str):
        return ""
    with object_store().materialize(key).open("rb") as handle:
        return handle.read(1600).decode("utf-8", errors="ignore")[:400]


def gather_inputs(session: Session, plan: ActionPlan, params: DraftLabelSetParams) -> DraftInputs:
    """Read standards, existing vocabularies, annotations and the frozen sample files."""
    categories, attributes = _standard_sources(session, params.standard_codes)
    categories += _label_set_sources(session, params.label_set_ids)
    annotated = _annotated(
        session,
        (*params.annotation_dataset_ids, *([params.dataset_id] if params.dataset_id else [])),
    )
    for sample_labels in annotated.values():
        categories += [
            CategorySource(key=value, name_zh=value, origin="annotation")
            for value in sorted(sample_labels)
        ]
    vision = params.profile == "cloud-vision"
    samples = tuple(
        SampleSource(
            id=file.id,
            filename=file.filename,
            modality=file.modality,
            text=_text(file),
            image_data_url=_image(file) if vision else None,
            labels=tuple(sorted(annotated.get(file.id, set()))),
        )
        for file in (selected_files(session, plan) if params.sample_ids else [])
    )
    return DraftInputs(
        name=params.name,
        topic=params.topic,
        language=params.language,
        categories=tuple(categories),
        attributes=tuple(attributes),
        samples=samples,
    )


def _draft(inputs: DraftInputs, params: DraftLabelSetParams) -> DraftOutcome:
    if params.profile == "offline":
        return offline_draft(inputs)
    with httpx.Client(timeout=get_settings().provider_timeout, trust_env=False) as client:
        return model_draft(inputs, params.profile, params.max_cost_usd, client)


def execute_label_draft(
    session: Session, plan: ActionPlan, params: DraftLabelSetParams
) -> OperationResult:
    """Store the checked draft as a new unpublished label set version with its sources."""
    inputs = gather_inputs(session, plan, params)
    outcome = _draft(inputs, params)
    created = create_label_set(
        session,
        CreateLabelSetParams(
            request_id=params.request_id,
            name=params.name,
            labels=outcome.labels,
            guidelines=outcome.guidelines,
        ),
    )
    source = DraftSource(
        standard_codes=params.standard_codes,
        label_set_ids=params.label_set_ids,
        annotation_dataset_ids=params.annotation_dataset_ids,
        dataset_id=params.dataset_id,
        version_id=params.version_id,
        sample_ids=tuple(sample.id for sample in inputs.samples),
        profile=params.profile,
        model=outcome.model,
        input_tokens=outcome.input_tokens,
        output_tokens=outcome.output_tokens,
        cost_usd=outcome.cost_usd,
        plan_id=plan.id,
        drafted_at=utcnow(),
        dropped_examples=outcome.dropped_examples,
    )
    value = created.model_copy(update={"draft_source": source})
    row = label_set_row(session, value.id, value.version, lock=True)
    row.payload = value.model_dump(mode="json")
    session.flush()
    return OperationResult(
        outputs=[AssetRef(asset_type="label_set", asset_id=value.id, version=str(value.version))],
        details={
            "label_set_id": value.id,
            "version": value.version,
            "labels": len(value.labels),
            "model": outcome.model,
            "cost_usd": outcome.cost_usd,
            "dropped_examples": outcome.dropped_examples,
        },
    )
