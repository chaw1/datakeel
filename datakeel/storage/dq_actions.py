# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Bind approved quality mutations to rule revisions and catalog target facts."""

from sqlalchemy.orm import Session

from datakeel.actions.dq_parameters import (
    ChangeQualityIssueParams,
    CreateQualityRuleParams,
    DeleteQualityRuleParams,
    QualityActionParams,
    RunQualityRuleParams,
    UpdateQualityRuleParams,
)
from datakeel.actions.models import ActionPlan, OperationResult
from datakeel.core.catalog_canonical import document_hash
from datakeel.core.catalog_models import CatalogSnapshot, SourceProperties, TableProperties
from datakeel.core.dq_models import DqRule
from datakeel.core.errors import ConflictError, ValidationError
from datakeel.core.models import AssetRef, BoundaryModel, JsonDocument
from datakeel.quality.dq_source import validate_assertion
from datakeel.quality.dq_types import check_column_types
from datakeel.storage.catalog_action_state import catalog_state
from datakeel.storage.catalog_store import read_snapshot
from datakeel.storage.dataset_service import require_dataset
from datakeel.storage.dq_issues import change_issue, get_issue
from datakeel.storage.dq_store import delete_rule, get_rule, rule_revision, upsert_rule


def _catalog_table(
    snapshot: CatalogSnapshot, source_id: str, name: str, schema: str | None, role: str
) -> tuple[TableProperties, str | None]:
    candidates = [
        item
        for item in snapshot.objects
        if item.asset_ref.asset_type == "table"
        and item.source_id == source_id
        and item.name == name
        and (schema is None or item.schema_name == schema)
    ]
    if len(candidates) != 1:
        msg = f"Quality {role} table must resolve to exactly one catalog table"
        raise ValidationError(msg)
    return TableProperties.model_validate(candidates[0].properties.root), candidates[0].schema_name


def _check_types(
    snapshot: CatalogSnapshot, rule: DqRule, table: TableProperties, source: SourceProperties
) -> None:
    """Refuse column kinds whose values the read-only executor cannot evaluate."""
    if rule.target.column is None:
        return
    reference_type = None
    if rule.params.reference_table and rule.params.reference_column:
        reference, _ = _catalog_table(
            snapshot,
            rule.target.source_id,
            rule.params.reference_table,
            rule.params.reference_schema or rule.target.schema_name,
            "reference",
        )
        if rule.params.reference_column not in reference.columns:
            msg = "Quality reference column is not in the catalog table"
            raise ValidationError(msg)
        reference_type = reference.columns[rule.params.reference_column]
    check_column_types(rule, table.columns[rule.target.column], source.dialect, reference_type)


def _resolve_target(session: Session, rule: DqRule) -> DqRule:
    if rule.dataset_id is not None:
        require_dataset(session, rule.dataset_id)
    snapshot = read_snapshot(session)
    table, schema = _catalog_table(
        snapshot, rule.target.source_id, rule.target.table, rule.target.schema_name, "target"
    )
    if rule.target.column is not None and rule.target.column not in table.columns:
        msg = "Quality target column is not in the catalog table"
        raise ValidationError(msg)
    rule = rule.model_copy(
        update={"target": rule.target.model_copy(update={"schema_name": schema})}
    )
    sources = [
        item
        for item in snapshot.objects
        if item.asset_ref.asset_type == "source" and item.source_id == rule.target.source_id
    ]
    if len(sources) != 1:
        msg = "Quality source is not registered in the catalog"
        raise ValidationError(msg)
    source = SourceProperties.model_validate(sources[0].properties.root)
    if not source.connection_url or source.dialect not in {"sqlite", "postgres", "postgresql"}:
        msg = "Quality source must have a supported database connection"
        raise ValidationError(msg)
    if rule.kind == "sql_assertion":
        validate_assertion(rule, source)
    _check_types(snapshot, rule, table, source)
    return rule


def prepare_quality_params(session: Session, params: BoundaryModel) -> BoundaryModel:
    """Reject stale revisions and unresolved targets before issuing a reviewable plan."""
    if isinstance(params, CreateQualityRuleParams | UpdateQualityRuleParams):
        rule = _resolve_target(session, params.rule)
        expected = params.expected_revision if isinstance(params, UpdateQualityRuleParams) else None
        if rule_revision(session, params.rule.id) != expected:
            msg = "Quality rule revision changed"
            raise ConflictError(msg)
        return params.model_copy(
            update={"rule": rule.model_copy(update={"revision": (expected or 0) + 1})}
        )
    if isinstance(params, DeleteQualityRuleParams | RunQualityRuleParams):
        rule = get_rule(session, params.rule_id)
        if (
            isinstance(params, DeleteQualityRuleParams)
            and rule.revision != params.expected_revision
        ):
            msg = "Quality rule revision changed"
            raise ConflictError(msg)
    if isinstance(params, ChangeQualityIssueParams):
        issue = get_issue(session, params.issue_id)
        if issue.revision != params.expected_revision:
            msg = "Quality issue revision changed"
            raise ConflictError(msg)
    return params


def quality_state(session: Session, params: QualityActionParams) -> str:
    """Hash the exact quality target and metadata revisions used by the frozen plan."""
    if isinstance(params, ChangeQualityIssueParams):
        return document_hash(
            JsonDocument(get_issue(session, params.issue_id).model_dump(mode="json"))
        )
    identifier = (
        params.rule.id
        if isinstance(params, CreateQualityRuleParams | UpdateQualityRuleParams)
        else params.rule_id
        if isinstance(params, DeleteQualityRuleParams | RunQualityRuleParams)
        else ""
    )
    return document_hash(
        JsonDocument(
            {
                "rule_id": identifier,
                "revision": rule_revision(session, identifier),
                "catalog": catalog_state(session),
            }
        )
    )


def execute_quality_action(
    session: Session, plan: ActionPlan, params: QualityActionParams
) -> OperationResult:
    """Apply a checked mutation inside the existing action transaction."""
    if isinstance(params, CreateQualityRuleParams | UpdateQualityRuleParams):
        expected = params.expected_revision if isinstance(params, UpdateQualityRuleParams) else None
        rule = upsert_rule(session, params.rule, expected, plan.actor)
        return OperationResult(
            outputs=[
                AssetRef(asset_type="quality_rule", asset_id=rule.id, version=str(rule.revision))
            ],
            details={"rule_id": rule.id, "revision": rule.revision},
        )
    if isinstance(params, DeleteQualityRuleParams):
        rule = delete_rule(session, params.rule_id, params.expected_revision, plan.actor)
        return OperationResult(details={"rule_id": rule.id, "revision": rule.revision})
    if isinstance(params, ChangeQualityIssueParams):
        issue = change_issue(
            session,
            params.issue_id,
            params.status,
            params.assignee,
            params.expected_revision,
            plan.actor,
        )
        return OperationResult(details={"issue_id": issue.id, "status": issue.status})
    return _schedule_action(session, plan, params)


def _schedule_action(
    session: Session, plan: ActionPlan, params: QualityActionParams
) -> OperationResult:
    if isinstance(params, RunQualityRuleParams):
        # Scheduling remains in this transaction; publication is fenced by the task lease.
        from datakeel.storage.dq_jobs import schedule_rule  # noqa: PLC0415

        run = schedule_rule(session, params.rule_id, f"action:{plan.id}")
        return OperationResult(task_id=run.task_id, details={"quality_run_id": run.id})
    msg = "No quality action handler"
    raise ValidationError(msg)
