# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Quality edits retain the existing approval, snapshot and idempotency guarantees."""

from pathlib import Path

import pytest

from datakeel.actions.models import ApprovalDecision, ExecuteRequest
from datakeel.actions.service import approve_plan, execute_plan, prepare_action
from datakeel.core.dq_models import DqParameters
from datakeel.core.errors import AuthorizationError, ConflictError, ValidationError
from datakeel.core.models import JsonDocument
from datakeel.storage.database import Database
from datakeel.storage.dq_reads import read_history, read_rules
from tests.dq_support import execute_action, generated_rule, save_rule


def test_quality_create_requires_approval_and_replays_one_revision(
    db: Database, tmp_path: Path
) -> None:
    """A model-prepared edit cannot publish before human approval or execute twice."""
    rule = generated_rule(db, tmp_path)
    plan = prepare_action(
        db, "create_quality_rule", JsonDocument({"rule": rule.model_dump(mode="json")})
    )
    assert plan.requires_approval
    assert plan.impact.object_count == 1
    assert not plan.manifest.objects
    with pytest.raises(AuthorizationError):
        execute_plan(db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest))
    assert not read_rules(db)
    approve_plan(db, plan.id, ApprovalDecision(approve=True, plan_digest=plan.plan_digest))
    request = ExecuteRequest(plan_digest=plan.plan_digest, operation_id=plan.operation_id)
    first = execute_plan(db, plan.id, request)
    assert first.status == "SUCCEEDED"
    assert execute_plan(db, plan.id, request).id == first.id
    assert len(read_history(db, rule.id)) == 1


@pytest.mark.parametrize(
    "sql",
    [
        "UPDATE orders SET amount=0",
        "SELECT 1; SELECT 2",
        "SELECT * FROM missing",
        "WITH x AS (SELECT 1) SELECT * FROM x",
    ],
)
def test_quality_sql_assertion_rejects_unsafe_definition_before_execution(
    db: Database,
    tmp_path: Path,
    sql: str,
) -> None:
    """Unsafe SQL never becomes an approved executable quality definition."""
    rule = generated_rule(db, tmp_path).model_copy(
        update={"kind": "sql_assertion", "params": DqParameters(sql=sql)}
    )
    with pytest.raises(ValidationError):
        save_rule(db, rule)
    assert not read_rules(db)


def test_quality_prepare_resolves_unique_schema_from_catalog(db: Database, tmp_path: Path) -> None:
    """A default-schema input becomes an exact schema-qualified frozen definition."""
    rule = generated_rule(db, tmp_path)
    rule = rule.model_copy(update={"target": rule.target.model_copy(update={"schema_name": None})})
    save_rule(db, rule)
    assert read_rules(db)[0].target.schema_name == "main"


def test_quality_intervening_update_invalidates_approved_plan(db: Database, tmp_path: Path) -> None:
    """Two users reviewing revision one cannot overwrite each other's committed change."""
    rule = generated_rule(db, tmp_path)
    save_rule(db, rule)
    changed = rule.model_copy(update={"owner": "New owner"})
    params = JsonDocument({"rule": changed.model_dump(mode="json"), "expected_revision": 1})
    plan = prepare_action(db, "update_quality_rule", params)
    approve_plan(db, plan.id, ApprovalDecision(approve=True, plan_digest=plan.plan_digest))
    execute_action(db, "update_quality_rule", params)
    with pytest.raises(ConflictError, match="target state changed"):
        execute_plan(db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest))
    assert read_rules(db)[0].revision == 2
    assert [item.operation for item in read_history(db, rule.id)] == ["create", "update"]


def test_quality_delete_preserves_tombstone_and_cannot_reuse_identifier(
    db: Database, tmp_path: Path
) -> None:
    """Archiving stops future scheduling while retaining the full mutation history."""
    rule = generated_rule(db, tmp_path)
    save_rule(db, rule)
    execute_action(
        db, "delete_quality_rule", JsonDocument({"rule_id": rule.id, "expected_revision": 1})
    )
    assert read_rules(db) == ()
    assert [item.operation for item in read_history(db, rule.id)] == ["create", "delete"]
    with pytest.raises(ConflictError):
        save_rule(db, rule)


def test_quality_prepare_rejects_unresolved_targets_without_connecting(
    db: Database, tmp_path: Path
) -> None:
    """Rule plans resolve known catalog metadata and never probe an unregistered target."""
    rule = generated_rule(db, tmp_path)
    for target in (
        rule.target.model_copy(update={"source_id": "unknown"}),
        rule.target.model_copy(update={"table": "unknown"}),
        rule.target.model_copy(update={"column": "unknown"}),
    ):
        with pytest.raises(ValidationError, match="catalog"):
            save_rule(db, rule.model_copy(update={"target": target}))
    assert not read_rules(db)
