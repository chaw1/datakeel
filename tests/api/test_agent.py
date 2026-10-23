# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""SSE transport preserves controlled actions, replay, trace totals, and typed recovery."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from datakeel.agent.models import AgentEvent
from datakeel.agent.providers import FakeProvider
from datakeel.api.app import create_app
from datakeel.core.agent_models import ModelResponse, ToolCall
from datakeel.storage.dataset_service import import_paths
from tests.asgi_client import TestClient

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

    from httpx import Response

    from datakeel.storage.database import Database


@pytest.fixture
def agent_client(db: Database, tmp_path: Path) -> Iterator[tuple[TestClient, str]]:
    """Expose generated assets through the actual HTTP transport and offline demo provider."""
    empty = tmp_path / "empty.txt"
    empty.write_text("", encoding="utf-8")
    healthy = tmp_path / "healthy.txt"
    healthy.write_text("A complete generated example containing useful quality evidence.")
    dataset = import_paths(db, "agent-api", [empty, healthy])
    with TestClient(create_app(db)) as client:
        yield client, dataset.id


def events(response: Response) -> list[AgentEvent]:
    """Decode full typed events rather than accepting raw SSE string fragments."""
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/event-stream")
    return [
        AgentEvent.model_validate_json(line.removeprefix("data: "))
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]


def test_conversation_when_quarantining_emits_receipt_and_replays_without_extra_calls(
    agent_client: tuple[TestClient, str],
) -> None:
    """Exercise search, lazy action discovery, automatic execution, and exact idempotent replay."""
    client, dataset_id = agent_client
    session = client.post("/api/agent/conversations", json={"dataset_id": dataset_id}).json()
    url = f"/api/agent/conversations/{session['id']}/messages"
    body = {"content": "隔离质量低于 1 分的文本", "idempotency_key": "one-request"}
    first = events(client.post(url, json=body))
    names = [event.call.name for event in first if event.call]
    assert names == ["search_files", "tool_search", "quarantine_files"]
    assert [event.event for event in first][-4:] == ["plan", "receipt", "text", "done"]
    assert events(client.post(url, json=body)) == first
    traces = client.get("/api/harness/traces", params={"conversation_id": session["id"]}).json()
    assert len(traces) == 4
    for trace in traces:
        assert (
            sum(segment["tokens"] for segment in trace["segments"])
            == trace["usage"]["input_tokens"]
        )
        assert trace["price_version"]
    assert client.get("/api/harness/budgets").json()
    invocations = client.get(
        "/api/harness/invocations", params={"session_id": session["id"]}
    ).json()
    assert all(item["status"] == "SUCCEEDED" for item in invocations)
    assert any(item["asset_refs"] for item in invocations)
    assert len(client.get("/api/agent/conversations").json()) == 1
    assert client.post(url, json={**body, "content": "changed"}).status_code == 409


def test_conversation_when_deleting_requires_http_user_decision_before_recovered_receipt(
    agent_client: tuple[TestClient, str],
) -> None:
    """Pause deletion at a plan, then recover its receipt after explicit UI endpoint decisions."""
    client, dataset_id = agent_client
    session = client.post("/api/agent/conversations", json={"dataset_id": dataset_id}).json()
    streamed = events(
        client.post(
            f"/api/agent/conversations/{session['id']}/messages",
            json={"content": "删除质量低于 1 分的文本"},
        )
    )
    assert streamed[-2].stop_reason == "approval_required"
    plan = next(event.outcome.plan for event in streamed if event.event == "plan" and event.outcome)
    assert plan is not None
    assert client.get("/api/actions/runs").json() == []
    assert (
        client.post(
            f"/api/approvals/{plan.id}",
            json={
                "approve": True,
                "plan_digest": plan.plan_digest,
            },
        ).status_code
        == 200
    )
    run = client.post(
        f"/api/actions/{plan.id}/execute", json={"plan_digest": plan.plan_digest}
    ).json()
    assert run["receipt"]["on_behalf_of"].endswith(session["id"])
    recovered = client.get(f"/api/agent/conversations/{session['id']}").json()
    card = next(item for item in recovered["events"] if item["event"] == "plan")
    assert card["outcome"]["run"]["id"] == run["id"]
    assert len(client.get(f"/api/datasets/{dataset_id}/files").json()) == 1


@pytest.mark.parametrize("group_by", ["conversation", "day", "model"])
def test_costs_when_grouped_preserve_recorded_usage_totals(
    agent_client: tuple[TestClient, str],
    group_by: str,
) -> None:
    """Expose all three supported accounting groupings without repricing historical rows."""
    client, dataset_id = agent_client
    session = client.post("/api/agent/conversations", json={"dataset_id": dataset_id}).json()
    events(
        client.post(
            f"/api/agent/conversations/{session['id']}/messages", json={"content": "列出数据集"}
        )
    )
    rows = client.get("/api/harness/costs", params={"group_by": group_by}).json()
    assert len(rows) == 1
    assert rows[0]["calls"] == 2
    assert rows[0]["input_tokens"] > 0
    assert rows[0]["group_by"] == group_by
    assert client.get("/api/harness/costs?group_by=invalid").status_code == 422


def test_stream_when_provider_injected_records_stop_and_respects_budget_before_call(
    db: Database,
) -> None:
    """Return an explicit stop event without spending a model call when reservation fails."""
    app = create_app(db)
    fake = FakeProvider([ModelResponse(tool_calls=[ToolCall(name="list_datasets")])])
    app.state.agent_provider = fake
    with TestClient(app) as client:
        session = client.post(
            "/api/agent/conversations",
            json={
                "budget": {"conversation_tokens": 1},
            },
        ).json()
        streamed = events(
            client.post(
                f"/api/agent/conversations/{session['id']}/messages", json={"content": "hello"}
            )
        )
        assert streamed[0].stop_reason == "budget_exceeded"
        assert streamed[-1].event == "done"
        assert fake.requests == []
        assert client.get("/api/harness/traces").json() == []


def test_conversation_when_missing_or_invalid_returns_domain_status_before_stream(
    agent_client: tuple[TestClient, str],
) -> None:
    """Resolve input/domain failures before sending successful SSE response headers."""
    client, _dataset_id = agent_client
    assert client.get("/api/agent/conversations/missing").status_code == 404
    assert (
        client.post(
            "/api/agent/conversations/missing/messages", json={"content": "hello"}
        ).status_code
        == 404
    )
    assert (
        client.post("/api/agent/conversations", json={"dataset_id": "missing"}).status_code == 404
    )
    schema = client.get("/api/openapi.json").json()
    assert "AgentEvent" in schema["components"]["schemas"]
