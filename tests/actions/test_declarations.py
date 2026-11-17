# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Owner closure, independent authority and genuinely consumed lifecycle metadata."""

from pathlib import Path

import pytest
from pydantic import ValidationError as ModelError
from sqlalchemy.orm import Session

from datakeel.action_store import file_handlers
from datakeel.action_store.lifecycle import prepared, stage
from datakeel.action_store.validation import validate_declarations
from datakeel.actions import file_declarations
from datakeel.actions.authorization import AUTHORIZATION, authorization_for
from datakeel.actions.declarations import ActionFrame, Condition
from datakeel.actions.ir import action_ir, file_assignments, vocabulary
from datakeel.actions.models import ActionContext, ApprovalDecision, ExecuteRequest
from datakeel.actions.parameters import PARAMETER_TYPES, SelectionParams
from datakeel.actions.production_language import PRODUCTION_LANGUAGE
from datakeel.actions.registry import POLICIES, action_definitions
from datakeel.actions.service import approve_plan, execute_plan, prepare_action
from datakeel.agent.confirm import execute_reversible
from datakeel.core.data_asset_models import AccessContext
from datakeel.core.errors import AuthorizationError, ConflictError, DatakeelError, ValidationError
from datakeel.core.models import JsonDocument
from datakeel.ontology.tool_models import ToolCallContext, ToolOutcome
from datakeel.storage.database import Database
from datakeel.storage.production_human import require_production_human
from tests.actions.conftest import DatasetFixture


def test_ir_keeps_all_owners_in_original_policy_order() -> None:
    """Only the reversible pair owns structured semantics; legacy claims remain opaque."""
    items = action_ir()
    assert len(items) == 65
    assert [item.id for item in items] == list(POLICIES)
    assert [item.id for item in action_definitions()] == list(POLICIES)
    assert {item.id for item in items if item.owner == "generated"} == {
        "quarantine_files",
        "unquarantine_files",
    }
    assert all(not item.legacy_projection for item in items if item.owner == "generated")
    assert all(
        item.legacy_projection and item.semantics == "opaque"
        for item in items
        if item.owner == "legacy"
    )
    assert [effect.value for effect in file_assignments(items)] == [True, False]
    assert len(vocabulary().public) == 28
    assert {
        "data_asset",
        "quality_rule",
        "standard",
        "release",
        "training_split",
        "custom_operator",
        "action_run",
    } <= set(vocabulary().references)
    assert all(str(Path.home()) not in item.model_dump_json() for item in items)


def test_declaration_models_reject_extra_and_mutation() -> None:
    """The independent policy and declaration contracts are frozen and closed."""
    declaration = file_declarations.DECLARATIONS[0]
    for model in (
        declaration,
        declaration.authorization,
        declaration.approval,
        declaration.handlers,
        declaration.examples[0],
    ):
        assert model.model_config["frozen"]
        assert model.model_config["extra"] == "forbid"
        with pytest.raises(ModelError):
            type(model).model_validate({**model.model_dump(), "surprise": True})
    with pytest.raises(ModelError, match="frozen"):
        declaration.id = "other"


def test_startup_rejects_duplicate_owner(monkeypatch: pytest.MonkeyPatch) -> None:
    """An overlay cannot silently overwrite a duplicate generated owner."""
    monkeypatch.setattr(
        file_declarations,
        "DECLARATIONS",
        (*file_declarations.DECLARATIONS, file_declarations.DECLARATIONS[0]),
    )
    rejected = False
    try:
        validate_declarations()
    except ValueError as error:
        rejected = "Duplicate" in str(error)
    assert rejected, "Duplicate owners must fail startup"


@pytest.mark.parametrize("defect", ["inverse", "asset", "handler"])
def test_startup_rejects_dangling_contracts(monkeypatch: pytest.MonkeyPatch, defect: str) -> None:
    """Broken inverses, asset kinds and lifecycle handlers all fail closed."""
    declaration, inverse = file_declarations.DECLARATIONS
    updates = {
        "inverse": {"inverse": "unknown"},
        "asset": {"preconditions": (Condition(kind="opaque", asset="unknown"),)},
        "handler": {"handlers": declaration.handlers.model_copy(update={"execute": "absent"})},
    }
    monkeypatch.setattr(
        file_declarations, "DECLARATIONS", (declaration.model_copy(update=updates[defect]), inverse)
    )
    with pytest.raises(ValidationError):
        validate_declarations()


def test_language_deletion_cannot_enable_production_execution(
    db: Database, dataset: DatasetFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Presentation disappears while the independent human-only restriction remains."""
    plan = prepare_action(
        db, "quarantine_files", JsonDocument({"selection": {"dataset_id": dataset[0].id}})
    )
    production = plan.model_copy(update={"action_type": "split_packages"})
    monkeypatch.delitem(PRODUCTION_LANGUAGE, "split_packages")
    with pytest.raises(AuthorizationError, match="person"):
        require_production_human(
            production, AccessContext(actor="local", entry="agent", scope="query")
        )
    outcome = ToolOutcome(name="split_packages", status="SUCCEEDED", plan=production)
    assert execute_reversible(db, outcome, ToolCallContext(), dry_run=False) is None


def test_authorization_deletion_denies_both_entry_guards(
    db: Database, dataset: DatasetFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A missing authority record cannot become an automatic or unrestricted default."""
    plan = prepare_action(
        db, "quarantine_files", JsonDocument({"selection": {"dataset_id": dataset[0].id}})
    )
    plan = plan.model_copy(update={"action_type": "split_packages"})
    monkeypatch.delitem(AUTHORIZATION, "split_packages")
    with pytest.raises(AuthorizationError, match="explicit authorization"):
        require_production_human(plan, AccessContext(actor="local", entry="agent", scope="query"))
    outcome = ToolOutcome(name="split_packages", status="SUCCEEDED", plan=plan)
    with pytest.raises(AuthorizationError, match="explicit authorization"):
        execute_reversible(db, outcome, ToolCallContext(), dry_run=False)


def test_generated_handler_is_the_actual_file_state_owner(
    db: Database, dataset: DatasetFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Disabling a declared execute handler changes real execution, not just IR output."""
    plan = prepare_action(
        db, "quarantine_files", JsonDocument({"selection": {"dataset_id": dataset[0].id}})
    )

    def refuse(_session: object, _frame: ActionFrame) -> ActionFrame:
        msg = "declared-handler-refused"
        raise ValidationError(msg)

    monkeypatch.setattr(file_handlers, "quarantine", refuse)
    rejected = False
    try:
        execute_plan(db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest))
    except DatakeelError as error:
        rejected = "declared-handler-refused" in str(error)
    assert rejected, "Execution must consume the declared handler"


def test_dynamic_approval_cannot_be_relaxed_by_a_later_hook(
    db: Database, dataset: DatasetFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Remember tightening even if a later handler returns reversible=True."""

    def tighten(_session: object, frame: ActionFrame) -> ActionFrame:
        return frame.model_copy(update={"reversible": False})

    original_impact = file_handlers.impact

    def relax(session: Session, frame: ActionFrame) -> ActionFrame:
        return original_impact(session, frame).model_copy(update={"reversible": True})

    monkeypatch.setattr(file_handlers, "impact", relax)
    monkeypatch.setattr(file_handlers, "prepare", tighten)
    params = SelectionParams.model_validate({"selection": {"dataset_id": dataset[0].id}})
    with db.session() as session:
        frame = prepared("quarantine_files", session, ActionFrame(params=params))
    assert frame.reversible is False
    assert authorization_for("quarantine_files").automatic


def test_agent_quarantine_auto_execution_retains_attributed_receipt(
    db: Database, dataset: DatasetFixture
) -> None:
    """The allowed reversible pair still completes automatically with its owning identity."""
    context = ToolCallContext(agent_id="fixture", session_id="session")
    plan = prepare_action(
        db,
        "quarantine_files",
        JsonDocument({"selection": {"dataset_id": dataset[0].id}}),
        ActionContext(**context.model_dump()),
    )
    result = execute_reversible(
        db,
        ToolOutcome(name="quarantine_files", status="SUCCEEDED", plan=plan),
        context,
        dry_run=False,
    )
    assert result is not None
    assert result.run is not None
    assert result.run.receipt is not None
    assert result.run.receipt.on_behalf_of == "agent:fixture/session:session"


@pytest.mark.parametrize("phase", ["snapshot", "impact", "quarantine", "receipt"])
def test_unprepared_frames_cannot_cross_lifecycle_phase_boundaries(
    db: Database, phase: str
) -> None:
    """Wrong stage ordering must fail before a handler can claim or mutate targets."""
    frame = ActionFrame(params=SelectionParams.model_validate({"selection": {}}))
    handler = getattr(file_handlers, phase)
    with db.session() as session, pytest.raises(ConflictError, match="Incomplete"):
        handler(session, frame)


@pytest.mark.parametrize("missing", [False, True])
def test_runtime_rejects_removed_or_untyped_handler_results(
    db: Database, monkeypatch: pytest.MonkeyPatch, *, missing: bool
) -> None:
    """A corrupted binding after startup cannot bypass the typed result boundary."""
    monkeypatch.setattr(file_handlers, "quarantine", None if missing else lambda *_args: None)
    frame = ActionFrame(params=SelectionParams.model_validate({"selection": {}}))
    with db.session() as session, pytest.raises(ValidationError):
        stage("quarantine_files", "execute", session, frame)


def test_startup_rejects_deleted_authority_record(monkeypatch: pytest.MonkeyPatch) -> None:
    """The complete independent inventory is required before accepting any request."""
    monkeypatch.delitem(AUTHORIZATION, "split_packages")
    with pytest.raises(ValidationError, match="authorization inventory"):
        validate_declarations()


def test_examples_cannot_hide_mutable_selection_containers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A frozen wrapper cannot hide mutable list defaults inside legacy request models."""
    declaration, inverse = file_declarations.DECLARATIONS
    example = declaration.examples[0].model_copy(
        update={"params": SelectionParams.model_validate({"selection": {}})}
    )
    monkeypatch.setattr(
        file_declarations,
        "DECLARATIONS",
        (
            declaration.model_copy(update={"examples": (example,)}),
            inverse,
        ),
    )
    with pytest.raises(ValidationError, match="immutable tuples"):
        validate_declarations()


@pytest.mark.parametrize("action", ["quarantine_files", "delete_files"])
def test_mcp_cannot_cross_control_phase_even_with_an_existing_human_signature(
    db: Database, dataset: DatasetFixture, action: str
) -> None:
    """The backend enforces prepare-only independently of discovery and tool dispatch."""
    plan = prepare_action(db, action, JsonDocument({"selection": {"dataset_id": dataset[0].id}}))
    access = AccessContext(actor="local", entry="mcp", scope="query")
    decision = ApprovalDecision(approve=True, plan_digest=plan.plan_digest)
    request = ExecuteRequest(plan_digest=plan.plan_digest)
    with pytest.raises(AuthorizationError, match="MCP"):
        approve_plan(db, plan.id, decision, access=access)
    if plan.requires_approval:
        approve_plan(db, plan.id, decision)
    with pytest.raises(AuthorizationError, match="MCP"):
        execute_plan(db, plan.id, request, access=access)
    assert execute_plan(db, plan.id, request).status == "SUCCEEDED"


def test_deleted_legacy_owner_is_rejected_at_startup(monkeypatch: pytest.MonkeyPatch) -> None:
    """Deleting the complete declaration must not silently erase a public legacy owner."""
    monkeypatch.setattr(file_declarations, "DECLARATIONS", file_declarations.DECLARATIONS[1:])
    with pytest.raises(ValidationError, match="inventory"):
        validate_declarations()


def test_parameter_owner_overlay_preserves_historical_mcp_positions() -> None:
    """The real MCP catalog consumes parameter iteration order, independently of registry."""
    names = list(PARAMETER_TYPES)
    start = names.index("annotation_acceptance") + 1
    assert names[start : start + 3] == ["quarantine_files", "unquarantine_files", "delete_files"]
