# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Create catalog drafts and publish frozen vocabularies with exact migration impact."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from datakeel.actions.production_catalog_parameters import (
    CreateLabelSetParams,
    PublishLabelSetParams,
    RegisterModelParams,
    UpdateModelParams,
)
from datakeel.core.errors import ConflictError, ValidationError
from datakeel.core.models import new_id, utcnow
from datakeel.core.production_catalog_models import LabelSet, ProductionModel, ProductionTemplate
from datakeel.storage.production_catalog import label_set_row, require_label_set
from datakeel.storage.production_catalog_impact import migration_impact, validate_migration
from datakeel.storage.production_catalog_rows import (
    ProductionLabelSetRow,
    ProductionModelRow,
    ProductionTemplateRow,
)


def create_label_set(session: Session, params: CreateLabelSetParams) -> LabelSet:
    """Create a new draft version or edit a draft without ever rewriting a published one."""
    identifier = params.label_set_id or new_id()
    latest = session.scalar(
        select(func.max(ProductionLabelSetRow.version)).where(
            ProductionLabelSetRow.label_set_id == identifier
        )
    )
    version = params.version or (latest or 0) + 1
    if params.operation in {"update", "delete"}:
        row = label_set_row(session, identifier, version, lock=True)
        if row.published:
            message = "Published label sets are immutable; create a new version"
            raise ConflictError(message)
        if params.operation == "delete":
            value = LabelSet.model_validate(row.payload)
            session.delete(row)
            return value
    else:
        if session.scalar(
            select(ProductionLabelSetRow.id).where(
                ProductionLabelSetRow.label_set_id == identifier,
                ProductionLabelSetRow.version == version,
            )
        ):
            message = "Label set version already exists"
            raise ConflictError(message)
        row = ProductionLabelSetRow(id=new_id(), label_set_id=identifier, version=version)
    value = _draft(session, params, identifier, version)
    row.published = False
    row.payload = value.model_dump(mode="json")
    session.add(row)
    session.flush()
    return value


def _draft(
    session: Session, params: CreateLabelSetParams, identifier: str, version: int
) -> LabelSet:
    ids = {label.id for label in params.labels}
    names = {label.name for label in params.labels}
    if len(ids) != len(params.labels) or len(names) != len(params.labels):
        message = "Label identities and names must be unique"
        raise ValidationError(message)
    identities = {value: label.id for label in params.labels for value in (label.id, label.name)}
    if any(
        identities[label.id] != label.id or identities[label.name] != label.id
        for label in params.labels
    ):
        message = "Label names and identities cannot ambiguously overlap"
        raise ValidationError(message)
    parents = {label.id: label.parent_id for label in params.labels}
    for label in params.labels:
        seen = {label.id}
        parent = label.parent_id
        while parent is not None:
            if parent not in ids or parent in seen:
                message = "Label trees require existing parents and no cycles"
                raise ValidationError(message)
            seen.add(parent)
            parent = parents[parent]
    previous = params.previous_version
    if previous is None and version > 1:
        previous = version - 1
    value = LabelSet(
        id=identifier,
        version=version,
        name=params.name,
        labels=params.labels,
        previous_version=previous,
        migration=params.migration,
        created_at=utcnow(),
    )
    if previous is not None:
        before = require_label_set(session, identifier, previous)
        validate_migration(before, value)
        annotations, revisions = migration_impact(session, before, value)
        value = value.model_copy(
            update={
                "affected_annotations": annotations,
                "affected_revisions": revisions,
            }
        )
    return value


def publish_label_set(session: Session, params: PublishLabelSetParams) -> LabelSet:
    """Recount current exact migration impact and seal a vocabulary permanently."""
    row = label_set_row(session, params.label_set_id, params.version, lock=True)
    if row.published:
        message = "Label set version is already published"
        raise ConflictError(message)
    value = LabelSet.model_validate(row.payload)
    annotations, revisions = (0, 0)
    if value.previous_version is not None:
        before = require_label_set(session, value.id, value.previous_version)
        validate_migration(before, value)
        annotations, revisions = migration_impact(session, before, value)
    value = value.model_copy(
        update={
            "published": True,
            "published_at": utcnow(),
            "affected_annotations": annotations,
            "affected_revisions": revisions,
        }
    )
    row.published = True
    row.payload = value.model_dump(mode="json")
    session.flush()
    return value


def manage_template(session: Session, params: CreateLabelSetParams) -> ProductionTemplate:
    """Perform explicit create/update/archive operations through the declared catalog action."""
    template = params.template
    if template is None:
        message = "Template definition is required"
        raise ValidationError(message)
    row = session.get(
        ProductionTemplateRow,
        template.id,
        with_for_update=True,
        populate_existing=True,
    )
    if params.operation == "create":
        if row is not None:
            message = "Template identity already exists"
            raise ConflictError(message)
        value = template.model_copy(update={"revision": 1, "archived": False})
        row = ProductionTemplateRow(id=value.id, revision=1, payload=value.model_dump(mode="json"))
        session.add(row)
    else:
        if row is None or row.revision != template.revision:
            message = "Template revision changed or was not found"
            raise ConflictError(message)
        value = template.model_copy(
            update={
                "revision": row.revision + 1,
                "archived": params.operation == "delete",
            }
        )
        row.revision = value.revision
        row.payload = value.model_dump(mode="json")
    session.flush()
    return value


def save_model(session: Session, params: RegisterModelParams) -> ProductionModel:
    """Keep current model configuration optimistic while historical revisions retain attribution."""
    row = session.get(
        ProductionModelRow,
        params.model.id,
        with_for_update=True,
        populate_existing=True,
    )
    if isinstance(params, UpdateModelParams):
        if row is None or row.revision != params.expected_revision:
            message = "Model revision changed or was not found"
            raise ConflictError(message)
        value = params.model.model_copy(update={"revision": row.revision + 1})
        row.revision = value.revision
        row.payload = value.model_dump(mode="json")
    else:
        if row is not None:
            message = "Model identity already exists"
            raise ConflictError(message)
        value = params.model.model_copy(update={"revision": 1})
        session.add(
            ProductionModelRow(id=value.id, revision=1, payload=value.model_dump(mode="json"))
        )
    session.flush()
    return value
