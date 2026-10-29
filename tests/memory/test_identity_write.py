# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Explicit Agent memory writes obey the same server scope as HTTP memory writes."""

from collections.abc import Mapping

from datakeel.actions.models import ExecuteRequest
from datakeel.actions.service import execute_plan, prepare_action
from datakeel.api.app import create_app
from datakeel.core.agent_models import ToolCall
from datakeel.core.models import JsonDocument, new_id
from datakeel.memory.service import list_memories
from datakeel.memory.tools import invoke_memory
from datakeel.ontology.tool_models import ToolCallContext
from datakeel.storage.database import Database
from tests.asgi_client import TestClient


def _manage(db: Database, values: Mapping[str, object]) -> None:
    plan = prepare_action(
        db, "manage_users", JsonDocument.model_validate({"request_id": new_id(), **values})
    )
    execute_plan(db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest))


def _write(db: Database, actor: str) -> str:
    outcome = invoke_memory(
        db,
        ToolCall(
            id=new_id(),
            name="write_memory",
            arguments=JsonDocument({"content": "Generated explicit memory"}),
        ),
        ToolCallContext(actor=actor),
    )
    return outcome.status


def test_memory_write_zero_users_preserves_existing_tool_behavior(db: Database) -> None:
    """The existing single-user memory tool remains available before account registration."""
    assert _write(db, "unknown") == "SUCCEEDED"
    assert len(list_memories(db)) == 1


def test_registered_unknown_and_acceptance_cannot_write_memory_via_agent(db: Database) -> None:
    """The explicit memory tool cannot bypass the HTTP user-administration scope."""
    _manage(db, {"operation": "create", "user_id": "local"})
    _manage(db, {"operation": "create", "user_id": "observer", "role_ids": ["acceptance"]})
    for actor in ("unknown", "observer"):
        assert _write(db, actor) == "FAILED"
    assert list_memories(db) == []


def test_registered_authorized_actor_can_write_memory_via_agent(db: Database) -> None:
    """A registered user with the existing management scope retains explicit memory writes."""
    _manage(db, {"operation": "create", "user_id": "local"})
    _manage(db, {"operation": "create", "user_id": "writer", "role_ids": ["administrator"]})
    assert _write(db, "writer") == "SUCCEEDED"
    assert len(list_memories(db, actor="writer")) == 1


def test_http_memory_write_propagates_named_actor_after_local_is_disabled(db: Database) -> None:
    """The storage guard uses the actual authorized HTTP actor rather than a local default."""
    _manage(db, {"operation": "create", "user_id": "local"})
    _manage(db, {"operation": "create", "user_id": "writer", "role_ids": ["administrator"]})
    _manage(db, {"operation": "update", "user_id": "local", "status": "disabled"})
    with TestClient(create_app(db)) as client:
        response = client.post(
            "/api/agent/memories",
            json={"content": "Named authorized memory"},
            headers={"X-Datakeel-Actor": "writer"},
        )
        assert response.status_code == 200, response.text
    assert len(list_memories(db, actor="writer")) == 1
