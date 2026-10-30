# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""The MCP `assignees` read returns exactly what the cockpit's HTTP list returns."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from fastmcp import Client

from datakeel.api.app import create_app
from datakeel.core.workbench_models import WorkbenchAssignees
from datakeel.mcp import create_server
from datakeel.mcp.catalog import tool_definitions
from datakeel.ontology.tool_models import ToolOutcome
from tests.asgi_client import TestClient
from tests.production_helpers import production_fixture
from tests.production_team_ops import save, submit
from tests.production_team_support import ServiceRunner

if TYPE_CHECKING:
    from datakeel.storage.database import Database


def _mcp(db: Database, arguments: dict[str, object]) -> ToolOutcome:
    async def scenario() -> ToolOutcome:
        async with Client(create_server(db), mode="legacy") as client:
            response = await client.call_tool("assignees", arguments, raise_on_error=False)
        return ToolOutcome.model_validate(response.structured_content)

    return asyncio.run(scenario())


def _http(db: Database, project_id: str, stage: str, actor: str | None) -> tuple[int, object]:
    headers = {"X-Datakeel-Actor": actor} if actor else {}
    response = TestClient(create_app(db)).get(
        f"/api/production/projects/{project_id}/assignees",
        params={"stage": stage},
        headers=headers,
    )
    return response.status_code, response.json()


def _team(db: Database, *, local_manager: bool) -> tuple[str, ServiceRunner]:
    """A team project whose annotator holds open, submitted and review work."""
    project, tasks = production_fixture(db, "group", count=4)
    runner = ServiceRunner(db)
    runner("manage_users", {"operation": "create", "user_id": "boss"})
    people = [("ann", "annotator"), ("rev", "reviewer")]
    if local_manager:
        people.append(("local", "project_manager"))
    for actor, role in people:
        runner("manage_users", {"operation": "create", "user_id": actor}, "boss")
        runner(
            "manage_users",
            {"operation": "bind_role", "user_id": actor, "role_id": role, "project_id": project.id},
            "boss",
        )
    runner("upgrade_project", {"project_id": project.id, "workflow_tier": "team"}, "boss")
    held = [task.id for task in tasks[:3]]
    runner("assign_tasks", {"task_ids": held, "actor": "ann"}, "boss")
    save(db, held[0], "ann")
    submit(db, held[0], "ann")
    return project.id, runner


def test_assignees_is_a_read_only_mcp_tool() -> None:
    """The tool is listed with the stage parameter the HTTP list takes."""
    tools = {item.name: item for item in tool_definitions()}
    assert "assignees" in tools
    tool = tools["assignees"]
    properties = tool.parameters.root["properties"]
    assert isinstance(properties, dict)
    assert set(properties) == {"project_id", "stage"}
    assert tool.description.startswith("Read assignees")


def test_mcp_assignees_matches_http_for_each_stage(db: Database) -> None:
    """`local` registered as a manager reads the same people and open loads both ways."""
    project_id, _ = _team(db, local_manager=True)
    for stage in ("annotation", "review"):
        status, body = _http(db, project_id, stage, "local")
        outcome = _mcp(db, {"project_id": project_id, "stage": stage})
        assert status == 200
        assert outcome.status == "SUCCEEDED", outcome.error
        assert outcome.content.root["data"] == body
    listed = WorkbenchAssignees.model_validate(
        _mcp(db, {"project_id": project_id}).content.root["data"]
    )
    # Three assigned, one submitted and waiting for review: two are still being annotated.
    assert {person.actor: person.current for person in listed.people}["ann"] == 2


def test_mcp_assignees_refused_like_unregistered_http(db: Database) -> None:
    """When `local` cannot assign, MCP fails with the same reason HTTP returns."""
    project_id, _ = _team(db, local_manager=False)
    status, body = _http(db, project_id, "annotation", None)
    outcome = _mcp(db, {"project_id": project_id, "stage": "annotation"})
    assert status == 403
    assert outcome.status == "FAILED"
    assert outcome.error is not None
    assert outcome.error in str(body)


def test_zero_user_mcp_assignees_matches_http(db: Database) -> None:
    """Before anyone registers there is nobody to list, over either transport."""
    project, _ = production_fixture(db, "group", count=2)
    status, body = _http(db, project.id, "annotation", None)
    outcome = _mcp(db, {"project_id": project.id})
    assert status == 200
    assert outcome.status == "SUCCEEDED", outcome.error
    assert outcome.content.root["data"] == body
    assert body == {"project_id": project.id, "stage": "annotation", "people": []}
