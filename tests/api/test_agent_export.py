# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Export authorized conversation reports with measured costs and safe audit history."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest

from datakeel.actions.models import ExecuteRequest
from datakeel.actions.service import execute_plan, prepare_action
from datakeel.agent.models import AgentEvent
from datakeel.agent.providers import FakeProvider
from datakeel.api.app import create_app
from datakeel.api.routes.agent import ConversationReport
from datakeel.core.agent_models import (
    ChatMessage,
    Conversation,
    ConversationCreate,
    ModelResponse,
    ToolCall,
)
from datakeel.core.harness_models import BudgetLimits, ModelCallTrace, TokenUsage
from datakeel.core.intent_models import IntentResult
from datakeel.core.models import AssetRef, JsonDocument, new_id
from datakeel.dataset_store.dataset_service import import_paths
from datakeel.ontology.tool_models import ToolCallContext, ToolInvocationStart, ToolOutcome
from datakeel.storage.conversation_secrets import get_canary
from datakeel.storage.conversation_store import store
from datakeel.storage.harness_rows import ModelCallTraceRow
from datakeel.storage.identity_sessions import bind_session_actor
from datakeel.storage.tool_invocations import begin_invocation, finish_invocation
from tests.asgi_client import TestClient
from tests.assets.entry_helpers import grant, publish, revoke

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

    from datakeel.storage.database import Database

URL = "/api/agent/conversations"
AT = datetime(2026, 1, 1, tzinfo=UTC)


def _history(db: Database, dataset_id: str) -> list[AgentEvent]:
    plan = prepare_action(
        db, "quarantine_files", JsonDocument({"selection": {"dataset_id": dataset_id}})
    )
    run = execute_plan(db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest))
    outcome = ToolOutcome(name=plan.action_type, status="SUCCEEDED", plan=plan, run=run)
    return [
        AgentEvent(event="intent", intent=IntentResult(kind="answer", text="Inspect quality")),
        AgentEvent(event="tool_call", call=ToolCall(name="quarantine_files")),
        AgentEvent(event="plan", outcome=outcome),
        AgentEvent(event="receipt", outcome=outcome),
        AgentEvent(event="text", text="Child observation", agent_path="main/catalog-analyst"),
        AgentEvent(event="done", agent_path="main/catalog-analyst"),
        AgentEvent(event="text", text="First answer"),
        AgentEvent(event="done"),
        AgentEvent(event="receipt", outcome=outcome),
        AgentEvent(event="text", text="Approved continuation"),
        AgentEvent(event="done"),
        AgentEvent(event="tool_call", call=ToolCall(name="inspect_metadata")),
        AgentEvent(
            event="tool_result",
            outcome=ToolOutcome(name="inspect_metadata", status="FAILED", error="fixture failure"),
        ),
        AgentEvent(event="text", text="Second answer"),
        AgentEvent(event="stopped", stop_reason="max_turns"),
        AgentEvent(event="done"),
    ]


def _telemetry(db: Database, conversation: Conversation, ordinal: int, dataset_id: str) -> None:
    trace = ModelCallTrace(
        id=f"trace-{ordinal}",
        reservation_id=f"reservation-{ordinal}",
        conversation_id=conversation.id,
        accounting_conversation_id=conversation.root_conversation_id or conversation.id,
        agent_path=conversation.agent_path,
        depth=conversation.depth,
        turn=1,
        provider="fake",
        model="export-model",
        segments=[],
        usage=TokenUsage(output_tokens=ordinal * 10),
        accounted_tokens=ordinal * 10,
        latency_ms=1,
        stop_reason="stop",
        tool_calls=1,
        cost_usd=Decimal("0.000000111") * ordinal,
        price_version="fixture",
        created_at=AT,
    )
    with db.session() as session:
        session.add(
            ModelCallTraceRow(
                id=trace.id,
                reservation_id=trace.reservation_id,
                conversation_id=conversation.id,
                accounting_conversation_id=trace.accounting_conversation_id,
                model=trace.model,
                day="2026-01-01",
                cost_nanos=int(trace.cost_usd * 1_000_000_000),
                payload=trace.model_dump(mode="json"),
                created_at=AT.timestamp(),
            )
        )
        session.commit()
    identifier = begin_invocation(
        db,
        ToolInvocationStart(
            name="inspect_metadata",
            arguments_digest="fixture",
            argument_keys=[],
            context=ToolCallContext(session_id=conversation.id),
            asset_refs=[AssetRef(asset_id=dataset_id)],
        ),
    )
    finish_invocation(
        db,
        ToolOutcome(
            invocation_id=identifier,
            name="inspect_metadata",
            status="SUCCEEDED" if ordinal == 1 else "FAILED",
            asset_refs=[AssetRef(asset_id=dataset_id)],
        ),
        elapsed_ms=ordinal + 1.75,
    )


@pytest.fixture
def report_client(db: Database, tmp_path: Path) -> Iterator[tuple[TestClient, Conversation]]:
    """Seed a real plan/receipt, metered specialist and two chronological user turns."""
    source = tmp_path / "generated.txt"
    source.write_text("Generated report fixture.")
    dataset = import_paths(db, "export-data", [source])
    root = store(
        db,
        Conversation(
            id="report-session",
            created_at=AT,
            turns=2,
            config=ConversationCreate(
                dataset_id=dataset.id,
                model="export-model",
                budget=BudgetLimits(conversation_tokens=1000),
            ),
            messages=[
                ChatMessage(role="user", content="Repeated request"),
                ChatMessage(role="assistant", content="First answer"),
                ChatMessage(role="user", content="Repeated request"),
                ChatMessage(role="assistant", content="Second answer"),
            ],
            events=[
                JsonDocument(event.model_dump(mode="json")) for event in _history(db, dataset.id)
            ],
        ),
    )
    child = store(
        db,
        Conversation(
            id="report-specialist",
            config=root.config,
            created_at=AT,
            parent_conversation_id=root.id,
            root_conversation_id=root.id,
            agent_name="catalog-analyst",
            agent_path="main/catalog-analyst",
            depth=1,
        ),
    )
    _telemetry(db, root, 1, dataset.id)
    _telemetry(db, child, 2, dataset.id)
    with TestClient(create_app(db)) as client:
        yield client, root


def _assert_report_values(text: str, root: Conversation) -> None:
    expected = [
        "export-model",
        "fake",
        "dry_run",
        "turns",
        "created_at",
        "exported_at",
        "budget",
        "1000",
        "total_tokens",
        "30",
        "total_cost_usd",
        "0.000000333",
        "total_tool_calls",
        "total_tool_elapsed_ms",
        "6.5",
        "fake/export-model",
        "catalog-analyst",
        "main/catalog-analyst",
        "inspect_metadata",
        "quarantine_files",
        "EXECUTED",
        "SUCCEEDED",
        "requires_approval",
        "FAILED",
        "max_turns",
    ]
    for value in (
        root.id,
        root.config.dataset_id,
        *expected,
        "| Agent | Path | Tokens |",
        "Cost (USD)",
        "Tool latency (ms)",
        "Failed tools",
        "Inspect quality",
        "fixture failure",
    ):
        assert value is not None
        assert value in text


def test_markdown_report_contains_metadata_telemetry_receipts_and_chronological_transcript(
    report_client: tuple[TestClient, Conversation],
) -> None:
    """Download independently auditable values without losing specialist or turn order."""
    client, root = report_client
    response = client.get(f"{URL}/{root.id}/export")
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/markdown")
    assert (
        response.headers["content-disposition"]
        == 'attachment; filename="datakeel-conversation-report-session.md"'
    )
    _assert_report_values(response.text, root)
    outcome = next(
        event.root["outcome"] for event in root.events if event.root["event"] == "receipt"
    )
    assert isinstance(outcome, dict)
    for key in ("plan", "run"):
        item = outcome[key]
        assert isinstance(item, dict)
        assert str(item["id"]) in response.text
    transcript = response.text.split("## Chronological Transcript", 1)[1]
    turns = transcript.split("> User: Repeated request")
    assert len(turns) == 3
    assert turns[1].index("Child observation") < turns[1].index("First answer")
    assert turns[1].index("First answer") < turns[1].index("Approved continuation")
    assert "Second answer" not in turns[1]
    assert turns[2].index("inspect_metadata") < turns[2].index("Second answer")


def test_json_report_validates_typed_schema_and_retains_precise_costs(
    report_client: tuple[TestClient, Conversation],
) -> None:
    """The JSON download retains the same frozen report contract as its OpenAPI schema."""
    client, root = report_client
    response = client.get(f"{URL}/{root.id}/export?format=json")
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("application/json")
    assert response.headers["content-disposition"].endswith('report-session.json"')
    report = ConversationReport.model_validate_json(response.text)
    assert report.conversation.id == root.id
    assert report.conversation.messages == root.messages
    assert report.exported_at >= root.created_at
    assert report.call_tree.total_tokens == 30
    assert report.call_tree.total_cost_usd == Decimal("0.000000333")
    assert report.call_tree.total_tool_elapsed_ms == 6.5
    assert report.call_tree.nodes[1].failed_tools == 1
    schema = client.get("/api/openapi.json").json()
    content = schema["paths"][f"{URL}/{{conversation_id}}/export"]["get"]["responses"]["200"][
        "content"
    ]
    assert content["application/json"]["schema"]["$ref"].endswith("/ConversationReport")
    assert "text/markdown" in content


def test_export_rejects_invalid_format_and_another_actor(
    db: Database,
    report_client: tuple[TestClient, Conversation],
) -> None:
    """Reject malformed formats and known session IDs owned by another caller."""
    client, root = report_client
    assert client.get(f"{URL}/{root.id}/export?format=xml").status_code == 422
    plan = prepare_action(
        db,
        "manage_users",
        JsonDocument({"request_id": new_id(), "operation": "create", "user_id": "local"}),
    )
    execute_plan(db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest))
    bind_session_actor(db, root.id, "other")
    for export_format in ("markdown", "json"):
        denied = client.get(f"{URL}/{root.id}/export?format={export_format}")
        assert denied.status_code in {403, 404}, denied.text
        own = client.get(
            f"{URL}/{root.id}/export?format={export_format}", headers={"X-Datakeel-Actor": "other"}
        )
        assert own.status_code == 200, own.text


def test_export_rechecks_current_data_asset_grants(
    db: Database,
    report_client: tuple[TestClient, Conversation],
) -> None:
    """Revocation projects away previously readable derived history in both downloads."""
    client, root = report_client
    assert root.config.dataset_id is not None
    asset = publish(db, AssetRef(asset_id=root.config.dataset_id))
    grant_id = grant(db, asset, "valid", "query")
    assert grant_id is not None
    assert "First answer" in client.get(f"{URL}/{root.id}/export").text
    revoke(db, grant_id)
    for export_format in ("markdown", "json"):
        response = client.get(f"{URL}/{root.id}/export?format={export_format}")
        assert response.status_code == 200, response.text
        assert "Repeated request" in response.text
        assert "First answer" not in response.text
        assert "fixture failure" not in response.text


@pytest.mark.parametrize("export_format", ["markdown", "json"])
def test_export_does_not_leak_provider_canary(db: Database, export_format: str) -> None:
    """A blocked model secret remains a stop reason, never exported provider output."""
    app = create_app(db)
    with TestClient(app) as client:
        identifier = client.post(URL, json={}).json()["id"]
        canary = get_canary(db, identifier)
        app.state.agent_provider = FakeProvider([ModelResponse(content=canary)])
        sent = client.post(
            f"{URL}/{identifier}/messages", json={"content": "Inspect quality", "mode": "agent"}
        )
        assert sent.status_code == 200, sent.text
        response = client.get(f"{URL}/{identifier}/export?format={export_format}")
        assert response.status_code == 200, response.text
        assert "canary_leak" in response.text
        assert canary not in response.text


@pytest.mark.parametrize("export_format", ["markdown", "json"])
def test_export_redacts_persisted_secrets_and_sanitizes_filename(
    db: Database,
    export_format: str,
) -> None:
    """User text, nested tool arguments and errors cannot leak credential or sentinel values."""
    secret = "sk-" + "fixture" * 4
    canary = "dkc_" + "abc123" * 4
    call = ToolCall(
        name="inspect_metadata",
        arguments=JsonDocument({"api_key": "opaque-fixture", canary: "fixture"}),
    )
    events = [
        AgentEvent(event="tool_call", call=call),
        AgentEvent(
            event="tool_result", outcome=ToolOutcome(name=call.name, status="FAILED", error=canary)
        ),
        AgentEvent(event="done"),
    ]
    root = store(
        db,
        Conversation(
            id='report"session',
            config=ConversationCreate(),
            messages=[ChatMessage(role="user", content=f"Inspect {secret}")],
            events=[JsonDocument(event.model_dump(mode="json")) for event in events],
        ),
    )
    with TestClient(create_app(db)) as client:
        response = client.get(f"{URL}/{root.id}/export?format={export_format}")
    assert response.status_code == 200, response.text
    assert (
        'filename="datakeel-conversation-report_session.' in response.headers["content-disposition"]
    )
    for hidden in (secret, canary, "opaque-fixture"):
        assert hidden not in response.text
    assert "Inspect" in response.text


def test_export_labels_ambiguous_interrupted_resume_without_inventing_turn_order(
    db: Database,
    report_client: tuple[TestClient, Conversation],
) -> None:
    """An extra completion without a receipt preserves ordered evidence and marks the gap."""
    client, root = report_client
    incomplete = root.model_copy(
        update={"id": "interrupted-session", "messages": root.messages[:1]}
    )
    store(db, incomplete)
    response = client.get(f"{URL}/{incomplete.id}/export")
    assert response.status_code == 200, response.text
    assert "Turn correlation unavailable" in response.text
    assert "Messages" in response.text
    assert "Execution events" in response.text
    assert response.text.index("First answer") < response.text.index("Second answer")
