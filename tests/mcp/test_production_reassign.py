# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Taking `local`'s work back and assigning it by name decide the same way over HTTP and MCP."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from fastmcp import Client

from datakeel.actions.service import list_runs
from datakeel.api.app import create_app
from datakeel.mcp import create_server
from datakeel.ontology.tool_models import ToolOutcome
from tests.asgi_client import TestClient
from tests.production_helpers import production_fixture
from tests.production_team_support import ServiceRunner

if TYPE_CHECKING:
    from datakeel.storage.database import Database


def _mcp(db: Database, name: str, arguments: dict[str, object]) -> ToolOutcome:
    async def scenario() -> ToolOutcome:
        async with Client(create_server(db), mode="legacy") as client:
            response = await client.call_tool(name, arguments, raise_on_error=False)
        return ToolOutcome.model_validate(response.structured_content)

    return asyncio.run(scenario())


def _http(db: Database, name: str, body: dict[str, object], actor: str | None) -> tuple[int, str]:
    headers = {"X-Datakeel-Actor": actor} if actor else {}
    response = TestClient(create_app(db)).post(
        f"/api/actions/{name}/prepare", json=body, headers=headers
    )
    return response.status_code, response.text


def _calls(task_id: str) -> tuple[tuple[str, dict[str, object]], ...]:
    return (
        ("revoke_assignment", {"request_id": "r-1", "task_id": task_id, "reason": "local left"}),
        ("assign_tasks", {"request_id": "r-2", "task_ids": [task_id], "actor": "ann"}),
    )


def test_zero_user_mcp_only_prepares_take_back_and_named_assignment(db: Database) -> None:
    """Before anyone registers, MCP proposes both plans and nothing runs until a person signs."""
    _, tasks = production_fixture(db, "group", count=2)
    ServiceRunner(db)("assign_tasks", {"task_ids": [tasks[0].id], "actor": "local"})
    before = len(list_runs(db))
    for name, arguments in _calls(tasks[0].id):
        outcome = _mcp(db, name, arguments)
        assert outcome.status == "SUCCEEDED", outcome.error
        assert outcome.plan is not None
        assert outcome.plan.status == "PREPARED"
    assert len(list_runs(db)) == before


def test_after_team_upgrade_http_and_mcp_apply_the_same_authority_check(db: Database) -> None:
    """A manager prepares both plans over HTTP; MCP is refused like an unregistered HTTP actor.

    MCP always acts as `local`, and `local` itself is never registered here.
    """
    project, tasks = production_fixture(db, "group", count=2)
    runner = ServiceRunner(db)
    runner("assign_tasks", {"task_ids": [tasks[0].id], "actor": "local"})
    runner("manage_users", {"operation": "create", "user_id": "boss"})
    runner("manage_users", {"operation": "create", "user_id": "ann"}, "boss")
    runner(
        "manage_users",
        {
            "operation": "bind_role",
            "user_id": "ann",
            "role_id": "annotator",
            "project_id": project.id,
        },
        "boss",
    )
    runner("upgrade_project", {"project_id": project.id, "workflow_tier": "team"}, "boss")
    before = len(list_runs(db))
    for name, arguments in _calls(tasks[0].id):
        assert _http(db, name, arguments, "boss")[0] == 200
        status, text = _http(db, name, arguments, None)
        outcome = _mcp(db, name, arguments)
        assert status == 403
        assert outcome.status == "FAILED"
        assert outcome.error is not None
        assert outcome.error in text
    assert len(list_runs(db)) == before
