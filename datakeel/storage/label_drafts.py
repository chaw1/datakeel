# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Execute an approved draft: read its sources, draft, and store an unpublished version."""

import base64
import io
from collections import defaultdict

import httpx
from PIL import Image, UnidentifiedImageError
from pydantic import Field, JsonValue
from pydantic import ValidationError as ModelValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from datakeel.actions.label_draft_parameters import DraftLabelSetParams
from datakeel.actions.models import ActionPlan, OperationResult
from datakeel.actions.production_catalog_parameters import CreateLabelSetParams
from datakeel.core.annotation_models import AnnotationBatch
from datakeel.core.errors import DatakeelError, ValidationError
from datakeel.core.label_guidelines import DraftSource
from datakeel.core.models import AssetRef, BoundaryModel, FileItem, utcnow
from datakeel.core.production_catalog_models import LabelSet
from datakeel.core.settings import get_settings
from datakeel.label_drafts.model import estimate_cost, model_draft
from datakeel.label_drafts.models import (
    AttributeSource,
    CategorySource,
    DraftInputs,
    DraftOutcome,
    SampleSource,
)
from datakeel.label_drafts.offline import offline_draft
from datakeel.label_drafts.standards import classify_standards
from datakeel.storage.action_selection import files_by_id, selected_files
from datakeel.storage.annotation_rows import AnnotationBatchRow
from datakeel.storage.database import Database
from datakeel.storage.objects import object_store
from datakeel.storage.production_catalog import annotation_categories, label_set_row
from datakeel.storage.production_catalog_changes import create_label_set
from datakeel.storage.production_catalog_rows import ProductionLabelSetRow
from datakeel.storage.standard_store import state_in_session

IMAGE_EDGE = 768
BATCH_LIMIT = 20
# Annotated samples a draft may cite as examples when existing annotations are a source.
ANNOTATED_SAMPLES = 12


class _Sources(BoundaryModel):
    """What a draft reads, gathered the same way when it is planned and when it runs."""

    categories: tuple[CategorySource, ...] = ()
    attributes: tuple[AttributeSource, ...] = ()
    notes: tuple[str, ...] = ()
    annotated: dict[str, tuple[str, ...]] = Field(default_factory=dict[str, tuple[str, ...]])
    examples: tuple[FileItem, ...] = ()


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


def _annotated(session: Session, datasets: tuple[str, ...]) -> dict[str, dict[str, set[str]]]:
    """Labels per annotated sample, grouped by the dataset that holds the sample."""
    found: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    if not datasets:
        return found
    rows = session.scalars(
        select(AnnotationBatchRow)
        .where(AnnotationBatchRow.dataset_id.in_(datasets))
        .order_by(AnnotationBatchRow.created_at.desc())
        .limit(BATCH_LIMIT)
    )
    for row in rows:
        for record in AnnotationBatch.model_validate(row.batch).annotations:
            found[row.dataset_id][record.sample_id].update(annotation_categories(record))
    return found


def _unique(categories: list[CategorySource]) -> tuple[CategorySource, ...]:
    """One source per key and name, so a category seen on many samples is counted once."""
    keys: set[str] = set()
    names: set[str] = set()
    kept: list[CategorySource] = []
    for item in categories:
        name = item.name_zh.casefold()
        if item.key in keys or (item.parent_key is None and name in names):
            continue
        keys.add(item.key)
        names.add(name)
        kept.append(item)
    return tuple(kept)


def draft_sources(session: Session, params: DraftLabelSetParams) -> _Sources:
    """Standards, vocabularies, annotations and annotated example files of one draft.

    Planning budgets with exactly these counts and execution checks the same counts, so a
    draft approved at its estimate is never refused for counting its sources differently.
    """
    contract = state_in_session(session).contract
    standards = classify_standards(contract, params.standard_codes, params.language)
    categories = [*standards.categories, *_label_set_sources(session, params.label_set_ids)]
    datasets = (*params.annotation_dataset_ids, *([params.dataset_id] if params.dataset_id else []))
    grouped = _annotated(session, tuple(dict.fromkeys(datasets)))
    annotated = {
        sample: tuple(sorted(labels))
        for samples in grouped.values()
        for sample, labels in samples.items()
    }
    categories += [
        CategorySource(key=value, name_zh=value, origin="annotation")
        for value in sorted({label for labels in annotated.values() for label in labels})
    ]
    chosen = set(params.sample_ids)
    examples: list[FileItem] = []
    if params.annotation_dataset_ids:
        for dataset, samples in grouped.items():
            wanted = sorted(sample for sample in samples if sample not in chosen)
            examples += files_by_id(session, dataset, wanted)
    return _Sources(
        categories=_unique(categories),
        attributes=standards.attributes,
        notes=standards.notes,
        annotated=annotated,
        examples=tuple(examples[:ANNOTATED_SAMPLES]),
    )


def planned_draft_cost(db: Database, params: dict[str, JsonValue]) -> float:
    """The cost estimate execution will check, computed from the same sources."""
    profile = str(params.get("profile") or "offline")
    samples = params.get("sample_ids")
    count = len(samples) if isinstance(samples, list) else 0
    try:
        checked = DraftLabelSetParams.model_validate(
            {
                **params,
                "request_id": "estimate",
                "name": params.get("name") or "draft",
                "profile": "offline",
                "max_cost_usd": 0,
            }
        )
        with db.session() as session:
            sources = draft_sources(session, checked)
    except (ModelValidationError, DatakeelError):
        return estimate_cost(profile, count)
    return estimate_cost(profile, count + len(sources.examples), len(sources.categories))


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


def _sample(file: FileItem, labels: tuple[str, ...], *, vision: bool) -> SampleSource:
    return SampleSource(
        id=file.id,
        filename=file.filename,
        modality=file.modality,
        text=_text(file),
        image_data_url=_image(file) if vision else None,
        labels=labels,
    )


def gather_inputs(
    session: Session, plan: ActionPlan, params: DraftLabelSetParams
) -> tuple[DraftInputs, tuple[str, ...]]:
    """Read standards, existing vocabularies, annotations and the frozen sample files."""
    sources = draft_sources(session, params)
    vision = params.profile == "cloud-vision"
    files = [*(selected_files(session, plan) if params.sample_ids else []), *sources.examples]
    samples = tuple(
        _sample(file, sources.annotated.get(file.id, ()), vision=vision) for file in files
    )
    inputs = DraftInputs(
        name=params.name,
        topic=params.topic,
        language=params.language,
        categories=sources.categories,
        attributes=sources.attributes,
        samples=samples,
    )
    return inputs, sources.notes


def _draft(inputs: DraftInputs, params: DraftLabelSetParams) -> DraftOutcome:
    if params.profile == "offline":
        return offline_draft(inputs)
    with httpx.Client(timeout=get_settings().provider_timeout, trust_env=False) as client:
        return model_draft(inputs, params.profile, params.max_cost_usd, client)


def execute_label_draft(
    session: Session, plan: ActionPlan, params: DraftLabelSetParams
) -> OperationResult:
    """Store the checked draft as a new unpublished label set version with its sources."""
    inputs, notes = gather_inputs(session, plan, params)
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
        notes=notes,
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
