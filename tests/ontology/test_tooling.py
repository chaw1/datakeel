# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Shared tools always persist calls and keep preparation separate from execution."""

import pytest

from datakeel.actions.models import ActionContext
from datakeel.core.models import JsonDocument
from datakeel.ontology import tooling
from datakeel.ontology.models import ObjectSet
from datakeel.ontology.tool_models import ToolCallContext
from datakeel.ontology.tooling import invoke_tool
from datakeel.storage.database import Database
from datakeel.storage.object_queries import evaluate
from datakeel.storage.tool_invocations import list_invocations
from datakeel.storage.views import DatasetView


def test_read_tool_when_called_persists_summary_and_asset_refs(
    db: Database, dataset: DatasetView
) -> None:
    """Capture read status, caller, timing and actual result identities."""
    outcome = invoke_tool(db, "list_datasets", JsonDocument({}), ToolCallContext(session_id="read"))
    assert outcome.status == "SUCCEEDED"
    assert dataset.id in {ref.asset_id for ref in outcome.asset_refs}
    invocation = list_invocations(db, "read")[0]
    assert invocation.id == outcome.invocation_id
    assert invocation.asset_refs == outcome.asset_refs
    assert invocation.elapsed_ms >= 0


def test_action_tool_when_prepared_does_not_mutate_until_execute(
    db: Database, dataset: DatasetView
) -> None:
    """Return the frozen plan and reserve execution for an explicit control call."""
    selection = ObjectSet(dataset_id=dataset.id, quality_max=59)
    context = ToolCallContext(agent_id="demo", session_id="tools")
    plan = invoke_tool(
        db,
        "quarantine_files",
        JsonDocument({"selection": selection.model_dump(mode="json")}),
        context,
    )
    assert plan.plan is not None
    assert plan.requires_approval is False
    assert all(not item.properties["quarantined"] for item in evaluate(db, selection).objects)
    result = invoke_tool(
        db,
        "execute_plan",
        JsonDocument({"plan_id": plan.plan.id, "plan_digest": plan.plan.plan_digest}),
        context,
    )
    assert result.run is not None
    assert result.run.receipt is not None
    assert result.run.receipt.on_behalf_of == "agent:demo/session:tools"
    assert all(item.properties["quarantined"] for item in evaluate(db, selection).objects)


def test_delete_tool_when_explicitly_approved_executes_with_attributed_receipt(
    db: Database, dataset: DatasetView
) -> None:
    """Share the exact same approval binding between tool and HTTP adapters."""
    context = ToolCallContext(session_id="controlled")
    prepared = invoke_tool(
        db,
        "delete_files",
        JsonDocument({"selection": {"dataset_id": dataset.id, "quality_max": 0}}),
        context,
    )
    assert prepared.plan is not None
    assert prepared.requires_approval is True
    arguments = {"plan_id": prepared.plan.id, "plan_digest": prepared.plan.plan_digest}
    denied = invoke_tool(db, "execute_plan", JsonDocument(arguments), context)
    assert denied.status == "FAILED"
    approved = invoke_tool(
        db, "approve_plan", JsonDocument({**arguments, "approve": True}), context
    )
    assert approved.plan is not None
    assert approved.plan.status == "APPROVED"
    assert invoke_tool(db, "execute_plan", JsonDocument(arguments), context).status == "SUCCEEDED"
    assert len(list_invocations(db, "controlled")) == 4


@pytest.mark.parametrize(("name", "arguments"), [("absent", {}), ("get_quality", {"extra": 1})])
def test_invalid_tool_when_dispatched_persists_declared_failure(
    db: Database, name: str, arguments: dict[str, int]
) -> None:
    """Keep unknown-tool and argument-validation failures visible for loop guards."""
    result = invoke_tool(db, name, JsonDocument(arguments), ToolCallContext())
    assert result.status == "FAILED"
    assert list_invocations(db)[0].error


def test_tool_when_unexpected_exception_occurs_records_failure_and_reraises(
    db: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Preserve diagnostics without turning programmer failures into silent success."""
    message = "fixture storage failure"

    def fail(*_args: object, **_kwargs: object) -> ActionContext:
        raise RuntimeError(message)

    monkeypatch.setattr(tooling, "invoke_function", fail)
    with pytest.raises(RuntimeError, match=message):
        invoke_tool(db, "list_datasets", JsonDocument({}), ToolCallContext())
    assert list_invocations(db)[0].status == "FAILED"
