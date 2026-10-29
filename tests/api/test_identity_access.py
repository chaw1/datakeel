# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Close legacy HTTP write bypasses and preserve actual runtime caller identities."""

from pathlib import Path

import pytest

from datakeel.actions.models import ApprovalDecision, ExecuteRequest
from datakeel.actions.service import approve_plan, execute_plan, prepare_action
from datakeel.agent.providers import FakeProvider
from datakeel.api.app import create_app
from datakeel.api.identity_access import MUTATION_ACTIONS, READ_OR_CONTROLLED_ROUTES
from datakeel.core.agent_models import ModelResponse, ToolCall
from datakeel.core.models import JsonDocument, new_id
from datakeel.core.workflow_models import WorkflowEvent
from datakeel.storage.database import Database
from datakeel.storage.dataset_service import import_paths, list_versions
from datakeel.storage.identity_sessions import session_actor
from datakeel.storage.tool_invocations import list_invocations
from tests.asgi_client import TestClient


def _register(db: Database) -> None:
    plan = prepare_action(
        db,
        "manage_users",
        JsonDocument({"request_id": new_id(), "operation": "create", "user_id": "local"}),
    )
    execute_plan(db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest))


def test_every_http_mutation_has_an_explicit_identity_policy(db: Database) -> None:
    """A new business route cannot silently join the registered-user write surface."""
    app = create_app(db)
    actual = {
        (method.upper(), path)
        for path, methods in app.openapi()["paths"].items()
        for method in methods
        if method.upper() in {"POST", "PUT", "PATCH", "DELETE"}
    }
    assert actual == set(MUTATION_ACTIONS) | READ_OR_CONTROLLED_ROUTES


@pytest.mark.parametrize(("method", "route"), sorted(MUTATION_ACTIONS))
def test_unregistered_actor_cannot_use_legacy_http_write_routes(
    db: Database, method: str, route: str
) -> None:
    """Every direct business write is rejected before its endpoint can borrow local authority."""
    _register(db)
    with TestClient(create_app(db)) as client:
        path = route
        for name in (
            "identifier",
            "ordinal",
            "code_hash",
            "dataset_id",
            "document_id",
            "memory_id",
            "version_id",
            "run_id",
        ):
            path = path.replace("{" + name + "}", "unknown")
        response = client.request(method, path, json={}, headers={"X-Datakeel-Actor": "unknown"})
        assert response.status_code == 403, response.text


def test_zero_user_http_behavior_and_registered_read_post_remain_available(db: Database) -> None:
    """Zero-user writes retain legacy validation while registered anonymous reads still work."""
    with TestClient(create_app(db)) as client:
        assert client.post("/api/datasets", json={}).status_code == 422
        _register(db)
        assert (
            client.post(
                "/api/datasets", json={}, headers={"X-Datakeel-Actor": "unknown"}
            ).status_code
            == 403
        )
        assert (
            client.get("/api/datasets", headers={"X-Datakeel-Actor": "unknown"}).status_code == 200
        )
        response = client.post(
            "/api/ontology/object-sets/evaluate", json={}, headers={"X-Datakeel-Actor": "unknown"}
        )
        assert response.status_code == 200, response.text


def test_legacy_datasheet_preparation_uses_real_registered_actor(
    db: Database, tmp_path: Path
) -> None:
    """An authorized named caller is preserved in legacy prepared plans instead of local."""
    file = tmp_path / "text.txt"
    file.write_text("Generated identity fixture.")
    dataset = import_paths(db, "identity-data", [file])
    _register(db)
    role = prepare_action(
        db,
        "define_role",
        JsonDocument(
            {
                "request_id": new_id(),
                "role_id": "editor",
                "name": "Editor",
                "scopes": ["datasets:write"],
            }
        ),
    )
    approve_plan(db, role.id, ApprovalDecision(approve=True, plan_digest=role.plan_digest))
    execute_plan(db, role.id, ExecuteRequest(plan_digest=role.plan_digest))
    user = prepare_action(
        db,
        "manage_users",
        JsonDocument(
            {
                "request_id": new_id(),
                "operation": "create",
                "user_id": "editor",
                "role_ids": ["editor"],
            }
        ),
    )
    execute_plan(db, user.id, ExecuteRequest(plan_digest=user.plan_digest))
    with TestClient(create_app(db)) as client:
        response = client.post(
            f"/api/datasets/{dataset.id}/datasheets",
            json={"version_id": list_versions(db, dataset.id)[0].id},
            headers={"X-Datakeel-Actor": "editor"},
        )
        assert response.status_code == 200, response.text
        assert response.json()["actor"] == "editor"


def _metadata_write_provider(dataset_id: str) -> FakeProvider:
    return FakeProvider(
        [
            ModelResponse(
                tool_calls=[
                    ToolCall(
                        id="search",
                        name="tool_search",
                        arguments=JsonDocument({"query": "save_metadata"}),
                    )
                ]
            ),
            ModelResponse(
                tool_calls=[
                    ToolCall(
                        id="write",
                        name="save_metadata",
                        arguments=JsonDocument(
                            {
                                "dataset_id": dataset_id,
                                "values": {"forged": True},
                                "reason": "forged",
                            }
                        ),
                    )
                ]
            ),
            ModelResponse(content="Finished."),
        ]
    )


def test_agent_read_session_cannot_borrow_local_administrator_for_writes(
    db: Database, tmp_path: Path
) -> None:
    """Anonymous sessions can ask questions but action tools receive their actual identity."""
    file = tmp_path / "text.txt"
    file.write_text("Generated identity fixture.")
    dataset = import_paths(db, "identity-data", [file])
    _register(db)
    app = create_app(db)
    app.state.agent_provider = _metadata_write_provider(dataset.id)
    headers = {"X-Datakeel-Actor": "unknown"}
    with TestClient(app) as client:
        conversation = client.post("/api/agent/conversations", json={}, headers=headers).json()
        identifier = conversation["id"]
        assert session_actor(db, identifier) == "unknown"
        response = client.post(
            f"/api/agent/conversations/{identifier}/messages",
            json={"content": "Attempt metadata write"},
            headers=headers,
        )
        assert response.status_code == 200, response.text
        spans = list_invocations(db, identifier)
        attempted = next(span for span in spans if span.name == "save_metadata")
        assert attempted.actor == "unknown"
        assert attempted.status == "FAILED"
        other = client.post(
            f"/api/agent/conversations/{identifier}/messages",
            json={"content": "Borrow session"},
            headers={"X-Datakeel-Actor": "local"},
        )
        assert other.status_code == 403, other.text
        for suffix in ("", "/tree", "/audit", "/routes"):
            denied = client.get(
                f"/api/agent/conversations/{identifier}{suffix}",
                headers={"X-Datakeel-Actor": "local"},
            )
            assert denied.status_code == 403, denied.text
        assert (
            client.get("/api/agent/conversations", headers={"X-Datakeel-Actor": "local"}).json()
            == []
        )
        assert client.get("/api/agent/conversations", headers=headers).json()[0]["id"] == identifier


def test_workflow_binds_actual_actor_and_replay_rejects_another_owner(
    db: Database, tmp_path: Path
) -> None:
    """Deterministic tools use the caller's authority and start keys cannot transfer ownership."""
    file = tmp_path / "text.txt"
    file.write_text("Generated workflow identity fixture.")
    dataset = import_paths(db, "identity-workflow", [file])
    _register(db)
    body = {"idempotency_key": "identity-workflow", "inputs": {"dataset_id": dataset.id}}
    with TestClient(create_app(db)) as client:
        response = client.post(
            "/api/workflows/dataset-health/runs", json=body, headers={"X-Datakeel-Actor": "unknown"}
        )
        assert response.status_code == 200, response.text
        events = [
            WorkflowEvent.model_validate_json(line.removeprefix("data: "))
            for line in response.text.splitlines()
            if line.startswith("data: ")
        ]
        run = events[-1].run
        assert run.status == "FAILED"
        assert session_actor(db, run.id) == "unknown"
        assert all(span.actor == "unknown" for span in list_invocations(db, run.id))
        replay = client.post(
            "/api/workflows/dataset-health/runs", json=body, headers={"X-Datakeel-Actor": "local"}
        )
        assert replay.status_code == 403, replay.text
        resume = client.post(
            f"/api/workflows/runs/{run.id}/resume",
            json={"plan_id": "none", "idempotency_key": "resume"},
            headers={"X-Datakeel-Actor": "local"},
        )
        assert resume.status_code == 403, resume.text
        for suffix in ("", "/audit"):
            denied = client.get(
                f"/api/workflows/runs/{run.id}{suffix}", headers={"X-Datakeel-Actor": "local"}
            )
            assert denied.status_code == 403, denied.text
        assert client.get("/api/workflows/runs", headers={"X-Datakeel-Actor": "local"}).json() == []
        assert (
            client.get("/api/workflows/runs", headers={"X-Datakeel-Actor": "unknown"}).json()[0][
                "id"
            ]
            == run.id
        )
