# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Publish imported semantic drafts only after the existing signed action gate."""

from sqlalchemy.orm import Session

from datakeel.actions.catalog_parameters import ConfirmMetricDraftParams
from datakeel.actions.models import ActionPlan, OperationResult
from datakeel.core.catalog_models import CatalogObject, CatalogSnapshot
from datakeel.core.catalog_projection import snapshot_events
from datakeel.core.errors import ConflictError, NotFoundError, ValidationError
from datakeel.core.metadata_imports import MetricDraft
from datakeel.core.models import BoundaryModel, JsonDocument
from datakeel.metrics.projection import build_snapshot, metric_cards, semantic_layer
from datakeel.storage.catalog_store import (
    lock_catalog,
    publish_snapshot_in_session,
    read_snapshot,
)
from datakeel.storage.events import all_events
from datakeel.storage.metric_audit import record_metric_audit
from datakeel.storage.metric_store import update_metric_in_session, validate_metric_update


class _DraftContext(BoundaryModel):
    snapshot: CatalogSnapshot
    item: CatalogObject
    draft: MetricDraft


def _context(session: Session, draft_id: str) -> _DraftContext:
    scopes: dict[str, CatalogSnapshot] = {}
    for _, snapshot in snapshot_events(all_events(session)):
        scopes[snapshot.scope] = snapshot
    for snapshot in scopes.values():
        for item in snapshot.objects:
            if item.asset_ref.asset_id == draft_id and item.asset_ref.asset_type == "metric_draft":
                return _DraftContext(
                    snapshot=snapshot,
                    item=item,
                    draft=MetricDraft.model_validate(item.properties.root),
                )
    msg = "Imported metric draft not found"
    raise NotFoundError(msg)


def prepare_confirmation(
    session: Session, params: ConfirmMetricDraftParams
) -> ConfirmMetricDraftParams:
    """Freeze a complete validated definition without installing it into semantics."""
    lock_catalog(session)
    context = _context(session, params.draft_id)
    if context.draft.source_deleted or context.draft.status == "confirmed":
        msg = "Metric draft is deleted or already confirmed"
        raise ConflictError(msg)
    definition = params.definition or context.draft.definition
    if definition is None:
        msg = "Metric draft requires a complete definition before confirmation"
        raise ValidationError(msg)
    catalog = read_snapshot(session)
    if any(
        item.asset_ref.asset_id == definition.id and item.asset_ref.asset_type != "metric"
        for item in catalog.objects
    ):
        msg = "Metric identity already belongs to another catalog object type"
        raise ValidationError(msg)
    current = next(
        (item.definition for item in metric_cards(catalog) if item.definition.id == definition.id),
        None,
    )
    if definition.version != (current.version if current else 1):
        msg = "Metric confirmation expected version does not match the semantic layer"
        raise ConflictError(msg)
    validate_metric_update(session, definition)
    return params.model_copy(update={"definition": definition})


def confirm_draft(
    session: Session, plan: ActionPlan, params: ConfirmMetricDraftParams
) -> OperationResult:
    """Commit approved semantics and the source's confirmation status atomically."""
    params = prepare_confirmation(session, params)
    definition = params.definition
    if definition is None:
        msg = "Prepared metric confirmation requires a definition"
        raise ValidationError(msg)
    context = _context(session, params.draft_id)
    catalog = read_snapshot(session)
    layer = semantic_layer(catalog)
    if any(item.id == definition.id for item in layer.metrics):
        change = update_metric_in_session(session, definition, plan.actor)
        record_metric_audit(session, plan, change)
        event_id = change.event_id
        definition = change.after.definition
    else:
        snapshot = build_snapshot(
            layer.model_copy(update={"metrics": [*layer.metrics, definition]}), catalog
        )
        report = publish_snapshot_in_session(session, snapshot, "METRIC_CHANGE", plan.actor)
        event_id = report.event_id
    confirmed = context.draft.model_copy(update={"status": "confirmed", "definition": definition})
    updated = context.item.model_copy(
        update={"properties": JsonDocument(confirmed.model_dump(mode="json"))}
    )
    snapshot = context.snapshot.model_copy(
        update={
            "objects": tuple(
                updated if item.asset_ref.asset_id == params.draft_id else item
                for item in context.snapshot.objects
            )
        }
    )
    publish_snapshot_in_session(session, snapshot, actor=plan.actor)
    return OperationResult(
        outputs=[
            updated.asset_ref,
            next(
                item.asset_ref
                for item in read_snapshot(session).objects
                if item.asset_ref.asset_id == definition.id
            ),
        ],
        details={"metric_id": definition.id, "draft_id": params.draft_id, "event_id": event_id},
    )
