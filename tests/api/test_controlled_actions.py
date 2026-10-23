# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""HTTP controlled mutations preserve approval binding, visible state, and receipts."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator
    from typing import Never, TextIO

    from httpx import Response
    from pydantic import JsonValue

    from datakeel.storage.database import Database

import importlib
from datetime import timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from jsonschema import Draft202012Validator
from sqlalchemy.orm import Session

from datakeel.api.app import create_app
from datakeel.core.models import utcnow
from datakeel.core.settings import get_settings
from datakeel.storage.dataset_service import import_paths
from datakeel.worker.runner import run_worker
from tests.asgi_client import TestClient


@pytest.fixture
def client_and_dataset(db: Database, tmp_path: Path) -> Iterator[tuple[TestClient, str]]:
    """Provide the client and dataset test fixture."""
    empty = tmp_path / "empty.txt"
    empty.write_text("", encoding="utf-8")
    good = tmp_path / "good.txt"
    good.write_text("Generated evidence with enough detail.", encoding="utf-8")
    created = import_paths(db, "controlled-example", [empty, good])
    with TestClient(create_app(db)) as client:
        yield client, created.id


def prepare(
    client: TestClient, dataset_id: str, action: str = "quarantine_files"
) -> dict[str, JsonValue]:
    """Provide the prepare test fixture."""
    response = client.post(
        f"/api/actions/{action}/prepare",
        json={"selection": {"dataset_id": dataset_id, "quality_max": 0}},
    )
    assert response.status_code == 200, response.text
    return response.json()


def approve(client: TestClient, plan: dict[str, JsonValue], *, accepted: bool = True) -> Response:
    """Provide the approve test fixture."""
    return client.post(
        f"/api/approvals/{plan['id']}",
        json={"approve": accepted, "plan_digest": plan["plan_digest"]},
    )


def execute(client: TestClient, plan: dict[str, JsonValue], **fields: JsonValue) -> Response:
    """Provide the execute test fixture."""
    return client.post(
        f"/api/actions/{plan['id']}/execute",
        json={"plan_digest": plan["plan_digest"], **fields},
    )


def test_ontology_endpoint_when_requested_exposes_valid_versioned_schemas(
    client_and_dataset: tuple[TestClient, str],
) -> None:
    """Verify ontology endpoint when requested exposes valid versioned schemas."""
    client, _dataset_id = client_and_dataset
    value = client.get("/api/ontology").json()
    assert len(value["object_types"]) == 13
    assert len(value["link_types"]) == 9
    assert len(value["functions"]) == 13
    assert len(value["actions"]) == 14
    for item in value["object_types"]:
        Draft202012Validator.check_schema(item["properties"])
    for item in value["actions"]:
        Draft202012Validator.check_schema(item["params_schema"])
        assert "compensation" not in item
    inverse = {item["id"]: item["inverse_of"] for item in value["actions"]}
    assert inverse["quarantine_files"] == "unquarantine_files"
    assert inverse["unquarantine_files"] == "quarantine_files"
    schema = client.get("/api/openapi.json").json()
    assert "compensation" not in schema["components"]["schemas"]["ActionType"]["properties"]
    assert "reason" in schema["components"]["schemas"]["ActionRun"]["properties"]


def test_object_set_endpoint_when_quality_filtered_returns_frozen_source_identity(
    client_and_dataset: tuple[TestClient, str],
) -> None:
    """Verify object set endpoint when quality filtered returns frozen source identity."""
    client, dataset_id = client_and_dataset
    value = client.post(
        "/api/ontology/object-sets/evaluate", json={"dataset_id": dataset_id, "quality_max": 0}
    ).json()
    assert [item["properties"]["filename"] for item in value["objects"]] == ["empty.txt"]
    assert value["objects"][0]["revision"]
    assert value["state_digest"]


def test_reversible_action_when_executed_needs_no_approval_and_updates_public_reads(
    client_and_dataset: tuple[TestClient, str],
) -> None:
    """Verify reversible action when executed needs no approval and updates public reads."""
    client, dataset_id = client_and_dataset
    plan = prepare(client, dataset_id)
    assert client.get("/api/approvals").json() == []
    response = execute(client, plan)
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "SUCCEEDED"
    files = client.get(f"/api/datasets/{dataset_id}/files").json()
    assert next(item for item in files if item["filename"] == "empty.txt")["metadata"][
        "quarantined"
    ]
    assert (
        client.get(f"/api/datasets/{dataset_id}/quality?quarantined=true").json()["file_count"] == 1
    )
    assert (
        client.get(f"/api/datasets/{dataset_id}/quality?quarantined=false").json()["file_count"]
        == 1
    )


def test_successful_execution_when_receipt_created_is_visible_in_lineage(
    client_and_dataset: tuple[TestClient, str],
) -> None:
    """Verify successful execution when receipt created is visible in lineage."""
    client, dataset_id = client_and_dataset
    run = execute(client, prepare(client, dataset_id)).json()
    graph = client.get("/api/lineage/graph", params={"asset": dataset_id}).json()
    assert any(edge["event_id"] == run["receipt"]["event_id"] for edge in graph["edges"])
    assert run["receipt"]["on_behalf_of"] == "local"
    assert any(node.get("quarantined") is True for node in graph["nodes"])
    assert client.get(f"/api/actions/plans/{run['plan_id']}").json()["status"] == "EXECUTED"
    assert client.get("/api/actions/runs").json()[0]["id"] == run["id"]


def test_irreversible_action_when_not_approved_records_denied_evidence(
    client_and_dataset: tuple[TestClient, str],
) -> None:
    """Verify missing approval denies execution while retaining a failure receipt."""
    client, dataset_id = client_and_dataset
    plan = prepare(client, dataset_id, "delete_files")
    assert client.get("/api/approvals").json()[0]["id"] == plan["id"]
    assert execute(client, plan).status_code == 403
    run = client.get("/api/actions/runs").json()[0]
    assert run["status"] == "DENIED"
    assert run["receipt"]["run_state"] == "FAIL"
    assert run["receipt"]["outputs"] == []
    assert len(client.get(f"/api/datasets/{dataset_id}/files").json()) == 2


@pytest.mark.parametrize(
    ("decision", "status_code", "reason"),
    [
        ("missing", 403, "AuthorizationError: Action requires explicit human approval"),
        ("rejected", 409, "ConflictError: Human approval was rejected"),
        (
            "consumed",
            409,
            "ConflictError: Action plan was already executed; approval was consumed",
        ),
    ],
)
def test_execute_when_unauthorized_exposes_distinct_denial_reason_and_legacy_error(
    client_and_dataset: tuple[TestClient, str], decision: str, status_code: int, reason: str
) -> None:
    """All three denials persist distinct reasons and replay as the same typed run."""
    client, dataset_id = client_and_dataset
    plan = prepare(client, dataset_id, "delete_files")
    if decision != "missing":
        assert approve(client, plan, accepted=decision == "consumed").status_code == 200
    if decision == "consumed":
        assert execute(client, plan).status_code == 200
    request = {"operation_id": plan["operation_id"]}
    assert execute(client, plan, **request).status_code == status_code
    denied = client.get("/api/actions/runs").json()[0]
    assert denied["status"] == "DENIED"
    assert denied["reason"] == denied["error"] == reason
    assert denied["receipt"]["run_state"] == "FAIL"
    assert denied["receipt"]["outputs"] == []
    replay = execute(client, plan, **request)
    assert replay.status_code == 200
    assert replay.json() == denied


def test_irreversible_action_when_rejected_cannot_execute(
    client_and_dataset: tuple[TestClient, str],
) -> None:
    """Verify irreversible action when rejected cannot execute."""
    client, dataset_id = client_and_dataset
    plan = prepare(client, dataset_id, "delete_files")
    assert approve(client, plan, accepted=False).json()["status"] == "REJECTED"
    assert execute(client, plan).status_code == 409
    assert client.get("/api/approvals").json() == []
    assert client.get("/api/actions/runs").json()[0]["status"] == "DENIED"
    assert client.get(f"/api/actions/plans/{plan['id']}").json()["status"] == "REJECTED"


def test_irreversible_action_when_approved_deletes_once_and_revokes_download(
    client_and_dataset: tuple[TestClient, str],
) -> None:
    """Verify irreversible action when approved deletes once and revokes download."""
    client, dataset_id = client_and_dataset
    plan = prepare(client, dataset_id, "delete_files")
    file_id = plan["manifest"]["objects"][0]["asset_ref"]["asset_id"]
    assert approve(client, plan).status_code == 200
    assert execute(client, plan).status_code == 200
    assert execute(client, plan).status_code == 409
    assert client.get("/api/actions/runs").json()[0]["status"] == "DENIED"
    assert client.get(f"/api/actions/plans/{plan['id']}").json()["status"] == "EXECUTED"
    assert client.get(f"/api/datasets/{dataset_id}/files/{file_id}/download").status_code == 404
    assert client.get(f"/api/datasets/{dataset_id}").json()["file_count"] == 1
    assert client.get(f"/api/datasets/{dataset_id}/quality").json()["file_count"] == 1


def test_approved_plan_when_parameters_changed_rejects_execution(
    client_and_dataset: tuple[TestClient, str],
) -> None:
    """Verify approved plan when parameters changed rejects execution."""
    client, dataset_id = client_and_dataset
    plan = prepare(client, dataset_id, "delete_files")
    approve(client, plan)
    changed = {
        **plan["canonical_params"],
        "selection": {"dataset_id": dataset_id, "quality_max": 100},
    }
    assert execute(client, plan, canonical_params=changed).status_code == 409
    assert len(client.get(f"/api/datasets/{dataset_id}/files").json()) == 2


def test_approved_plan_when_expired_rejects_execution(
    client_and_dataset: tuple[TestClient, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify approved plan when expired rejects execution."""
    client, dataset_id = client_and_dataset
    plan = prepare(client, dataset_id, "delete_files")
    approve(client, plan)
    future = utcnow() + timedelta(days=1)
    planning = importlib.import_module("datakeel.actions.policy")
    monkeypatch.setattr(planning, "utcnow", lambda: future)
    response = execute(client, plan)
    assert response.status_code == 409
    assert "expired" in response.json()["detail"]


@pytest.mark.parametrize("operation", ["approval", "execute"])
def test_action_request_when_body_spoofs_actor_is_forbidden(
    client_and_dataset: tuple[TestClient, str], operation: str
) -> None:
    """Verify action request when body spoofs actor is forbidden."""
    client, dataset_id = client_and_dataset
    plan = prepare(client, dataset_id, "delete_files")
    response = (
        client.post(
            f"/api/approvals/{plan['id']}",
            json={"approve": True, "plan_digest": plan["plan_digest"], "actor": "another-user"},
        )
        if operation == "approval"
        else execute(client, plan, actor="another-user")
    )
    assert response.status_code == 403


def test_action_prepare_when_actor_added_to_params_is_rejected(
    client_and_dataset: tuple[TestClient, str],
) -> None:
    """Verify action prepare when actor added to params is rejected."""
    client, dataset_id = client_and_dataset
    response = client.post(
        "/api/actions/quarantine_files/prepare",
        json={"selection": {"dataset_id": dataset_id}, "actor": "another-user"},
    )
    assert response.status_code == 422


def test_plan_details_when_missing_returns_not_found(
    client_and_dataset: tuple[TestClient, str],
) -> None:
    """Verify plan details when missing returns not found."""
    client, _dataset_id = client_and_dataset
    assert client.get("/api/actions/plans/missing").status_code == 404


def test_plan_when_digest_changed_is_rejected(client_and_dataset: tuple[TestClient, str]) -> None:
    """Verify plan when digest changed is rejected."""
    client, dataset_id = client_and_dataset
    plan = prepare(client, dataset_id, "delete_files")
    approve(client, plan)
    response = execute(client, plan, plan_digest="changed")
    assert response.status_code == 409
    assert "plan_digest" in response.json()["detail"]
    assert client.get("/api/actions/runs").json() == []


def test_approved_plan_when_target_revision_changes_is_rejected(
    client_and_dataset: tuple[TestClient, str],
) -> None:
    """Verify approved plan when target revision changes is rejected."""
    client, dataset_id = client_and_dataset
    plan = prepare(client, dataset_id, "delete_files")
    approve(client, plan)
    execute(client, prepare(client, dataset_id))
    response = execute(client, plan)
    assert response.status_code == 409
    assert "state changed" in response.json()["detail"]
    failed = client.get("/api/actions/runs").json()[0]
    assert failed["status"] == "FAILED"
    assert failed["reason"] is None


@pytest.mark.parametrize("export_format", ["croissant", "openlineage"])
def test_approved_export_when_unfrozen_payload_facts_change_rejects_execution(
    client_and_dataset: tuple[TestClient, str], export_format: str
) -> None:
    """Verify approved export when unfrozen payload facts change rejects execution."""
    client, dataset_id = client_and_dataset
    plan = client.post(
        "/api/actions/export_dataset/prepare",
        json={"dataset_id": dataset_id, "format": export_format, "destination": "reviewed.json"},
    ).json()
    assert approve(client, plan).status_code == 200
    if export_format == "croissant":
        client.put(
            f"/api/datasets/{dataset_id}/metadata",
            json={"values": {"description": "Added after approval"}, "reason": "changed evidence"},
        )
    else:
        client.post(
            "/api/lineage/events",
            json={
                "idempotency_key": "after-export-approval",
                "operator": "test.transform",
                "inputs": [{"asset_id": dataset_id}],
                "outputs": [{"asset_id": "new-output"}],
            },
        )
    assert execute(client, plan).status_code == 409


def test_queued_pipeline_when_target_deleted_before_worker_fails_without_output_receipt(
    db: Database, client_and_dataset: tuple[TestClient, str]
) -> None:
    """Verify queued pipeline when target deleted before worker fails without output receipt."""
    client, dataset_id = client_and_dataset
    pipeline = client.post(
        "/api/actions/run_pipeline/prepare", json={"dataset_id": dataset_id}
    ).json()
    run = execute(client, pipeline).json()
    deletion = prepare(client, dataset_id, "delete_files")
    approve(client, deletion)
    assert execute(client, deletion).status_code == 200
    run_worker(db, once=True)
    result = next(
        item for item in client.get("/api/actions/runs").json() if item["id"] == run["id"]
    )
    assert result["status"] == "FAILED"
    assert result["receipt"]["outputs"] == []


def test_export_when_business_commit_fails_removes_only_its_owned_artifact(
    client_and_dataset: tuple[TestClient, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify export when business commit fails removes only its owned artifact."""
    client, dataset_id = client_and_dataset
    plan = client.post(
        "/api/actions/export_dataset/prepare",
        json={"dataset_id": dataset_id, "destination": "rollback-export.json"},
    ).json()
    approve(client, plan)
    commit = Session.commit
    rejected = False

    def fail_first_commit(session: Session) -> None:
        """Provide the fail first commit test fixture."""
        nonlocal rejected
        if not rejected:
            rejected = True
            msg = "Injected business commit failure"
            raise RuntimeError(msg)
        return commit(session)

    monkeypatch.setattr(Session, "commit", fail_first_commit)
    with pytest.raises(RuntimeError, match="Injected business commit failure"):
        execute(client, plan)
    assert not (get_settings().home / "exports" / "rollback-export.json").exists()
    run = client.get("/api/actions/runs").json()[0]
    assert run["receipt"]["outputs"] == []


def test_accepted_pipeline_when_plan_ttl_passes_continues_without_reapproval(
    db: Database, client_and_dataset: tuple[TestClient, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify accepted pipeline when plan ttl passes continues without reapproval."""
    client, dataset_id = client_and_dataset
    pipeline = client.post(
        "/api/actions/run_pipeline/prepare", json={"dataset_id": dataset_id, "shards": 2}
    ).json()
    run = execute(client, pipeline).json()
    future = utcnow() + timedelta(days=1)
    policy = importlib.import_module("datakeel.actions.policy")
    monkeypatch.setattr(policy, "utcnow", lambda: future)
    run_worker(db, once=True)
    result = next(
        item for item in client.get("/api/actions/runs").json() if item["id"] == run["id"]
    )
    assert result["status"] == "SUCCEEDED"


def test_export_when_file_write_fails_removes_its_partial_artifact(
    client_and_dataset: tuple[TestClient, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify export when file write fails removes its partial artifact."""
    client, dataset_id = client_and_dataset
    plan = client.post(
        "/api/actions/export_dataset/prepare",
        json={"dataset_id": dataset_id, "destination": "partial-export.json"},
    ).json()
    approve(client, plan)

    original_open = Path.open

    def failed_open(
        path: Path, mode: str = "r", *, encoding: str | None = None
    ) -> TextIO | MagicMock:
        """Provide the failed open test fixture."""
        stream = original_open(path, mode, encoding=encoding)
        if path.name != "partial-export.json":
            return stream
        wrapped = MagicMock(wraps=stream)
        wrapped.__enter__.return_value = wrapped
        wrapped.__exit__.side_effect = stream.__exit__

        def failed_write(content: str) -> Never:
            """Provide the failed write test fixture."""
            stream.write(content[:10])
            msg = "Injected disk write failure"
            raise OSError(msg)

        wrapped.write.side_effect = failed_write
        return wrapped

    monkeypatch.setattr(Path, "open", failed_open)
    with pytest.raises(OSError, match="Injected disk write failure"):
        execute(client, plan)
    assert not (get_settings().home / "exports" / "partial-export.json").exists()
