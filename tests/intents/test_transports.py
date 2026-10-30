# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""People confirm chains over HTTP or the CLI; nobody else can run them, MCP cannot at all."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from fastmcp import Client

from datakeel.actions import service
from datakeel.agent.tools import deferred_tools, resident_tools
from datakeel.api.app import create_app
from datakeel.cli import parser
from datakeel.cli.intents import dispatch
from datakeel.core.intent_models import ActionChain, IntentResult, PageContext
from datakeel.mcp import create_server
from datakeel.mcp.catalog import tool_definitions
from tests.asgi_client import TestClient
from tests.intents.support import REASSIGN, SETUP, approve_waiting, images, plan, team
from tests.production_team_support import ServiceRunner

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

    from datakeel.storage.database import Database


def test_http_run_continues_after_signatures_and_reads_progress(
    db: Database, tmp_path: Path
) -> None:
    """The Web route runs as the request's person and stops at each signature."""
    dataset = images(db, tmp_path / "images")
    chain = plan(db, SETUP, PageContext(dataset_id=dataset.id)).chain
    assert chain is not None
    client = TestClient(create_app(db))
    first = ActionChain.model_validate(client.post(f"/api/intents/chains/{chain.id}/run").json())
    assert first.status == "awaiting_approval"
    while True:
        current = ActionChain.model_validate(client.get(f"/api/intents/chains/{chain.id}").json())
        if current.status != "awaiting_approval":
            break
        approve_waiting(db, current)
        client.post(f"/api/intents/chains/{chain.id}/run")
    assert current.status == "succeeded"


def test_http_refuses_another_person_and_changes_nothing(db: Database) -> None:
    """A chain asked for by boss cannot be read or run under another identity."""
    project, _ = team(db)
    chain = plan(db, REASSIGN, PageContext(project_id=project.id), actor="boss").chain
    assert chain is not None
    before = len(service.list_runs(db))
    client = TestClient(create_app(db))
    headers = {"X-Datakeel-Actor": "wang"}
    assert client.post(f"/api/intents/chains/{chain.id}/run", headers=headers).status_code == 403
    assert client.get(f"/api/intents/chains/{chain.id}", headers=headers).status_code == 403
    assert len(service.list_runs(db)) == before
    own = client.post(f"/api/intents/chains/{chain.id}/run", headers={"X-Datakeel-Actor": "boss"})
    assert own.status_code == 200
    assert ActionChain.model_validate(own.json()).status == "succeeded"


def test_cli_plans_offline_and_resumes_a_failed_chain(
    db: Database, capsys: pytest.CaptureFixture[str]
) -> None:
    """Planning, running and resuming are available from the terminal as a person."""
    project, _ = team(db)
    dispatch(
        db,
        parser().parse_args(
            ["intents", "plan", REASSIGN, "--project", project.id, "--actor", "boss"]
        ),
    )
    result = IntentResult.model_validate_json(capsys.readouterr().out)
    assert result.chain is not None
    dispatch(db, parser().parse_args(["intents", "run", result.chain.id, "--actor", "boss"]))
    finished = ActionChain.model_validate_json(capsys.readouterr().out)
    assert finished.status == "succeeded"
    dispatch(db, parser().parse_args(["intents", "show", result.chain.id, "--actor", "boss"]))
    assert ActionChain.model_validate_json(capsys.readouterr().out).id == result.chain.id


def test_no_agent_or_mcp_tool_can_run_or_confirm_a_chain(db: Database) -> None:
    """Chains are absent from every model-facing tool surface."""
    names = {tool.name for tool in [*resident_tools(), *deferred_tools(), *tool_definitions()]}

    async def listed() -> set[str]:
        async with Client(create_server(db), mode="legacy") as client:
            return {tool.name for tool in await client.list_tools()}

    exposed = names | asyncio.run(listed())
    assert not [name for name in exposed if "chain" in name or "intent" in name]


def test_new_web_conversations_use_the_configured_model(
    db: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The demo provider is only the fallback when no model key is configured."""
    client = TestClient(create_app(db))
    for name in ("DATAKEEL_OPENAI_API_KEY", "DATAKEEL_ANTHROPIC_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    route = "/api/agent/conversations/definitions/provider"
    assert client.get(route).json() == {"provider": "fake", "model": "fake-demo"}
    monkeypatch.setenv("DATAKEEL_OPENAI_API_KEY", "test-only")
    assert client.get(route).json() == {"provider": "openai", "model": "auto"}


def test_a_browser_signature_is_recorded_for_the_request_s_person(db: Database) -> None:
    """With registered users the placeholder signer is the requester; others are refused."""
    project, _ = team(db)
    values = {
        "name": "第二期",
        "dataset_id": project.dataset_id,
        "version_id": project.version_id,
        "label_set_id": project.label_set_id,
    }
    runner_plan = ServiceRunner(db).plan("create_project", values, "boss")
    assert runner_plan.requires_approval
    client = TestClient(create_app(db))
    decision = {"approve": True, "plan_digest": runner_plan.plan_digest}
    route = f"/api/approvals/{runner_plan.id}"
    headers = {"X-Datakeel-Actor": "boss"}
    refused = client.post(route, json={**decision, "actor": "li"}, headers=headers)
    assert refused.status_code == 403
    signed = client.post(route, json={**decision, "actor": "local"}, headers=headers)
    assert signed.status_code == 200, signed.text
    assert service.get_plan(db, runner_plan.id).status == "APPROVED"
