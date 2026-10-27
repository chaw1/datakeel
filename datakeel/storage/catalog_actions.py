# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Execute reversible metadata changes inside the existing action transaction."""

from sqlalchemy.orm import Session

from datakeel.actions.catalog_parameters import (
    CatalogActionParams,
    ConfirmMetricDraftParams,
    ImportCatalogParams,
    RestoreCatalogParams,
    RollbackMetricParams,
    RollbackTermParams,
    UpdateMetricParams,
    UpdateTermParams,
)
from datakeel.actions.models import ActionPlan, OperationResult
from datakeel.core.errors import ValidationError
from datakeel.core.models import AssetRef
from datakeel.storage.catalog_action_state import source_snapshot
from datakeel.storage.catalog_store import publish_snapshot_in_session
from datakeel.storage.metric_audit import record_metric_audit
from datakeel.storage.metric_drafts import confirm_draft
from datakeel.storage.metric_store import rollback_metric_in_session, update_metric_in_session
from datakeel.storage.term_changes import change_term, current_term, historical_term


def _import(
    session: Session, plan: ActionPlan, params: ImportCatalogParams | RestoreCatalogParams
) -> OperationResult:
    snapshot = (
        params.snapshot
        if isinstance(params, ImportCatalogParams)
        else source_snapshot(session, params.scope, params.version)
    )
    if snapshot is None:
        msg = "Catalog import requires a server-prepared snapshot"
        raise ValidationError(msg)
    report = publish_snapshot_in_session(session, snapshot, actor=plan.actor)
    if isinstance(params, ImportCatalogParams):
        report = report.model_copy(update={"parse_failures": params.parse_failures})
    return OperationResult(
        outputs=[item.asset_ref for item in snapshot.objects],
        details={
            "status": "unchanged" if report.event_id is None else "changed",
            "report": report.model_dump(mode="json"),
            "scope": snapshot.scope,
        },
    )


def _term(
    session: Session, plan: ActionPlan, params: UpdateTermParams | RollbackTermParams
) -> OperationResult:
    if isinstance(params, UpdateTermParams):
        definition, expected = params.definition, params.expected_revision
    else:
        definition = historical_term(session, params.term, params.revision)
        expected = current_term(session, params.term).revision
    after = change_term(session, definition, expected, plan.actor)
    return OperationResult(
        outputs=[after.asset_ref.model_copy(update={"version": str(after.revision)})],
        details={"from_version": expected, "to_version": after.revision},
    )


def execute_catalog_action(
    session: Session, plan: ActionPlan, params: CatalogActionParams
) -> OperationResult:
    """Dispatch metadata actions after the shared plan and snapshot checks pass."""
    if isinstance(params, ConfirmMetricDraftParams):
        return confirm_draft(session, plan, params)
    if isinstance(params, ImportCatalogParams | RestoreCatalogParams):
        return _import(session, plan, params)
    if isinstance(params, UpdateTermParams | RollbackTermParams):
        return _term(session, plan, params)
    if isinstance(params, UpdateMetricParams):
        change = update_metric_in_session(session, params.definition, plan.actor)
    elif isinstance(params, RollbackMetricParams):
        change = rollback_metric_in_session(session, params.metric_id, params.version, plan.actor)
    else:
        msg = "Unknown catalog action parameters"
        raise ValidationError(msg)
    record_metric_audit(session, plan, change)
    return OperationResult(
        outputs=[
            AssetRef(
                asset_type="metric",
                asset_id=change.after.definition.id,
                version=str(change.after.definition.version),
            )
        ],
        details={
            "metric_id": change.after.definition.id,
            "from_version": change.before.definition.version,
            "to_version": change.after.definition.version,
            "event_id": change.event_id,
        },
    )
