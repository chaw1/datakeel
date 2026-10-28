# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Human review, frozen state, reversible history and bounded standards mutation."""

from pathlib import Path

import pytest

from datakeel.actions.models import ActionContext, ApprovalDecision, ExecuteRequest
from datakeel.actions.registry import action_definition
from datakeel.actions.service import (
    approve_plan,
    execute_plan,
    list_approvals,
    list_runs,
    prepare_action,
)
from datakeel.core.errors import (
    AuthorizationError,
    BudgetError,
    ConflictError,
    NotFoundError,
    ValidationError,
)
from datakeel.core.models import JsonDocument
from datakeel.storage.database import Database
from datakeel.storage.standard_store import (
    get_contract,
    history,
    list_code_lists,
    list_mappings,
    list_standards,
)
from tests.standards_support import approved_change, install_standards, standard_contract


def test_standard_import_requires_explicit_human_approval(db: Database) -> None:
    """A reversible governance action cannot be automatically executed by an Agent."""
    params = JsonDocument({"contract": standard_contract().model_dump(mode="json")})
    plan = prepare_action(db, "import_standards", params)
    assert plan.reversible
    assert plan.requires_approval
    assert not plan.external
    assert [item.id for item in list_approvals(db)] == [plan.id]
    with pytest.raises(AuthorizationError, match="explicit human approval"):
        execute_plan(db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest))
    assert not get_contract(db).standards
    assert list_runs(db)[0].status == "DENIED"
    approve_plan(db, plan.id, ApprovalDecision(approve=True, plan_digest=plan.plan_digest))
    run = execute_plan(db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest))
    assert run.status == "SUCCEEDED"
    assert len(get_contract(db).standards) == 4
    with pytest.raises(ConflictError, match="consumed"):
        execute_plan(db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest))


def test_rejected_standard_plan_never_changes_state(db: Database) -> None:
    """Explicit rejection preserves an auditable denial and no business revision."""
    plan = prepare_action(db, "import_standards", JsonDocument({"contract": {}}))
    approve_plan(db, plan.id, ApprovalDecision(approve=False, plan_digest=plan.plan_digest))
    with pytest.raises(ConflictError, match="rejected"):
        execute_plan(db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest))
    assert not history(db).revisions
    assert list_runs(db)[0].status == "DENIED"


def test_field_and_code_edits_and_rollback_append_attributed_versions(
    db: Database, tmp_path: Path
) -> None:
    """New, changed and deprecated definitions remain recoverable through exact action history."""
    contract = install_standards(db, tmp_path)
    standard = contract.standards[0].model_copy(update={"status": "deprecated"})
    changed = approved_change(
        db, "update_standard", JsonDocument({"definition": standard.model_dump(mode="json")})
    )
    assert list_standards(db, "客户", "deprecated")[0].version == 2
    status = next(item for item in contract.standards if item.code == "status")
    approved_change(
        db,
        "update_standard",
        JsonDocument(
            {
                "definition": status.model_copy(update={"status": "deprecated"}).model_dump(
                    mode="json"
                )
            }
        ),
    )
    codes = contract.code_lists[0].model_copy(update={"status": "deprecated"})
    approved_change(
        db, "update_code_list", JsonDocument({"definition": codes.model_dump(mode="json")})
    )
    assert list_code_lists(db, "有效", "deprecated")[0].version == 2
    restored = approved_change(db, "rollback_standards", JsonDocument({"revision": 1}))
    current = get_contract(db)
    assert next(item for item in current.standards if item.code == standard.code).version == 3
    assert all(item.status == "active" for item in current.standards)
    assert current.code_lists[0].version == 3
    revisions = history(db).revisions
    assert [item.revision for item in revisions] == [1, 2, 3, 4, 5]
    assert revisions[1].plan_id == changed.plan_id
    assert revisions[-1].plan_id == restored.plan_id
    assert all(item.actor == "local" and item.event_id for item in revisions)
    assert action_definition("update_standard").inverse_of == "rollback_standards"


def test_confirmed_mapping_is_frozen_approved_and_reversible(db: Database, tmp_path: Path) -> None:
    """Confirmations require a real column, an active standard and an explicit decision."""
    install_standards(db, tmp_path)
    params = JsonDocument(
        {
            "mapping": {
                "column_id": "generated/main/customers/cust_id",
                "standard_code": "customer_id",
            }
        }
    )
    plan = prepare_action(db, "confirm_standard_mapping", params)
    assert plan.requires_approval
    assert not list_mappings(db)
    approve_plan(db, plan.id, ApprovalDecision(approve=True, plan_digest=plan.plan_digest))
    execute_plan(db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest))
    assert list_mappings(db)[0].standard_code == "customer_id"
    approved_change(db, "rollback_standards", JsonDocument({"revision": 1}))
    assert not list_mappings(db)
    with pytest.raises(NotFoundError, match="catalog column"):
        prepare_action(
            db,
            "confirm_standard_mapping",
            JsonDocument({"mapping": {"column_id": "absent", "standard_code": "customer_id"}}),
        )
    with pytest.raises(ValidationError, match="active"):
        prepare_action(
            db,
            "confirm_standard_mapping",
            JsonDocument(
                {
                    "mapping": {
                        "column_id": "generated/main/customers/cust_id",
                        "standard_code": "absent",
                    }
                }
            ),
        )


def test_intervening_standard_change_invalidates_approved_plan(
    db: Database, tmp_path: Path
) -> None:
    """Complete state freezes prevent a previously approved edit overwriting newer decisions."""
    contract = install_standards(db, tmp_path)
    field = contract.standards[0].model_copy(update={"owner": "New owner"})
    params = JsonDocument({"definition": field.model_dump(mode="json")})
    plan = prepare_action(db, "update_standard", params)
    approve_plan(db, plan.id, ApprovalDecision(approve=True, plan_digest=plan.plan_digest))
    approved_change(db, "update_standard", params)
    with pytest.raises(ConflictError, match="target state changed"):
        execute_plan(db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest))
    with pytest.raises(ConflictError, match="Expected"):
        prepare_action(db, "update_standard", params)


def test_standards_scope_versions_and_impact_are_enforced(db: Database) -> None:
    """Imports and rollback cannot hide multiple targets behind an empty file manifest."""
    params = JsonDocument({"contract": standard_contract().model_dump(mode="json")})
    with pytest.raises(AuthorizationError, match="scope"):
        prepare_action(db, "import_standards", params, ActionContext(scopes=["files:write"]))
    with pytest.raises(BudgetError, match="impact exceeds"):
        prepare_action(db, "import_standards", params, ActionContext(max_objects=1))
    approved_change(db, "import_standards", params)
    with pytest.raises(BudgetError, match="impact exceeds"):
        prepare_action(
            db, "rollback_standards", JsonDocument({"revision": 0}), ActionContext(max_objects=1)
        )
    with pytest.raises(NotFoundError, match="revision not found"):
        prepare_action(db, "rollback_standards", JsonDocument({"revision": 99}))
    approved_change(db, "rollback_standards", JsonDocument({"revision": 0}))
    assert not get_contract(db).standards


def test_restoration_after_empty_rollback_preserves_identity_version_history(db: Database) -> None:
    """Restoring an absent definition never reuses a historical identity version."""
    contract = standard_contract()
    approved_change(
        db, "import_standards", JsonDocument({"contract": contract.model_dump(mode="json")})
    )
    changed = contract.standards[0].model_copy(update={"owner": "Changed"})
    approved_change(
        db, "update_standard", JsonDocument({"definition": changed.model_dump(mode="json")})
    )
    approved_change(db, "rollback_standards", JsonDocument({"revision": 0}))
    approved_change(db, "rollback_standards", JsonDocument({"revision": 2}))
    restored = get_contract(db)
    assert next(item for item in restored.standards if item.code == changed.code).version == 3
    assert restored.code_lists[0].version == 2


def test_recreation_after_empty_rollback_advances_versions_and_rejects_stale_plan(
    db: Database,
) -> None:
    """A fresh create uses version one as input while storage advances historical identity."""
    contract = standard_contract()
    params = JsonDocument({"contract": contract.model_dump(mode="json")})
    stale = prepare_action(db, "import_standards", params)
    approve_plan(db, stale.id, ApprovalDecision(approve=True, plan_digest=stale.plan_digest))
    approved_change(db, "import_standards", params)
    approved_change(db, "rollback_standards", JsonDocument({"revision": 0}))
    with pytest.raises(ConflictError, match="target state changed"):
        execute_plan(db, stale.id, ExecuteRequest(plan_digest=stale.plan_digest))
    approved_change(db, "import_standards", params)
    recreated = get_contract(db)
    assert all(item.version == 2 for item in recreated.standards)
    assert recreated.code_lists[0].version == 2
    with pytest.raises(ConflictError, match="Expected"):
        prepare_action(db, "import_standards", params)


def test_code_list_deprecation_is_rejected_while_active_fields_depend_on_it(db: Database) -> None:
    """Reference data cannot be retired beneath an active field's declared value domain."""
    contract = standard_contract()
    approved_change(
        db, "import_standards", JsonDocument({"contract": contract.model_dump(mode="json")})
    )
    retired = contract.code_lists[0].model_copy(update={"status": "deprecated"})
    with pytest.raises(ValueError, match="active code list"):
        prepare_action(
            db, "update_code_list", JsonDocument({"definition": retired.model_dump(mode="json")})
        )


def test_receipts_keep_entity_versions_separate_from_mapping_snapshot_revisions(
    db: Database, tmp_path: Path
) -> None:
    """Mapping changes do not fabricate column revisions or inflate a field's own version."""
    contract = install_standards(db, tmp_path)
    for column, standard in (("cust_id", "customer_id"), ("status", "status")):
        run = approved_change(
            db,
            "confirm_standard_mapping",
            JsonDocument(
                {
                    "mapping": {
                        "column_id": f"generated/main/customers/{column}",
                        "standard_code": standard,
                    }
                }
            ),
        )
        assert run.receipt is not None
        assert {item.asset_type for item in run.receipt.outputs} == {
            "standard_mapping",
            "action_run",
        }
        assert any(
            item.asset_type == "column" and item.version is None for item in run.receipt.inputs
        )
    field = contract.standards[0].model_copy(update={"owner": "Changed owner"})
    run = approved_change(
        db, "update_standard", JsonDocument({"definition": field.model_dump(mode="json")})
    )
    assert run.receipt is not None
    fields = [item for item in run.receipt.outputs if item.asset_type == "standard"]
    assert len(fields) == 1
    assert fields[0].version == "2"
    assert history(db).revisions[-1].revision == 4
