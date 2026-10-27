# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""HTTP review material and scheduling preserve the existing approval boundary."""

from pathlib import Path

import pytest

from datakeel.api.app import create_app
from datakeel.core.settings import get_settings
from datakeel.storage.database import Database
from datakeel.storage.dataset_service import import_paths
from tests.asgi_client import TestClient

CODE = """PARAMETER_SCHEMA = {"type": "object", "properties": {}, "additionalProperties": False}
OUTPUT_METADATA_SCHEMA = {"type": "object", "properties": {}, "additionalProperties": False}
import socket

def run(inputs, params, ctx):
    return []
"""


def _submit(client: TestClient, code: str = CODE) -> dict[str, object]:
    response = client.post(
        "/api/custom-operators", json={"name": "review-example", "code": code, "modality": "any"}
    )
    assert response.status_code == 201, response.text
    return response.json()


def _approve(client: TestClient, plan: dict[str, object]) -> None:
    decision = client.post(
        f"/api/approvals/{plan['id']}",
        json={"approve": True, "plan_digest": plan["plan_digest"]},
    )
    assert decision.status_code == 200, decision.text
    execution = client.post(
        f"/api/actions/{plan['id']}/execute", json={"plan_digest": plan["plan_digest"]}
    )
    assert execution.status_code == 200, execution.text
    assert execution.json()["status"] == "SUCCEEDED"


def test_submission_when_pending_exposes_complete_code_and_advisory_findings(db: Database) -> None:
    """Submitting code keeps it visible for review and unavailable for pipeline execution."""
    with TestClient(create_app(db)) as client:
        plan = _submit(client)
        assert plan["reversible"] is False
        pending = client.get("/api/custom-operators/submissions").json()
        assert pending[0]["canonical_params"]["code"] == CODE
        assert pending[0]["canonical_params"]["static_checks"]
        assert client.get("/api/custom-operators").json() == []
        assert client.get("/api/custom-operators/runs").json() == []
        denied = client.post(
            f"/api/actions/{plan['id']}/execute", json={"plan_digest": plan["plan_digest"]}
        )
        assert denied.status_code == 403


def test_approved_code_when_modified_creates_a_separate_pending_version(db: Database) -> None:
    """Approval only publishes the reviewed digest; edited source needs another review."""
    with TestClient(create_app(db)) as client:
        first = _submit(client)
        _approve(client, first)
        approved = client.get("/api/custom-operators").json()
        assert len(approved) == 1
        version = approved[0]
        details = client.get(f"/api/custom-operators/{version['code_hash']}").json()
        assert details["code"] == CODE
        assert details["approved_by"] == "local"
        second = _submit(client, CODE + "\n# A separate revision\n")
        assert second["plan_digest"] != first["plan_digest"]
        assert len(client.get("/api/custom-operators").json()) == 1
        assert len(client.get("/api/custom-operators/submissions").json()) == 2


def test_run_endpoint_when_approved_schedules_the_exact_hash(db: Database, tmp_path: Path) -> None:
    """The HTTP convenience entry queues the same controlled immutable pipeline action."""
    source = tmp_path / "generated.txt"
    source.write_text("Generated fixture.\n", encoding="utf-8")
    dataset = import_paths(db, "custom-http", [source])
    with TestClient(create_app(db)) as client:
        _approve(client, _submit(client))
        version = client.get("/api/custom-operators").json()[0]
        response = client.post(
            f"/api/custom-operators/{version['code_hash']}/runs",
            json={"dataset_id": dataset.id, "params": {}},
        )
        assert response.status_code == 202, response.text
        run = response.json()
        assert run["status"] == "QUEUED"
        plan = client.get(f"/api/actions/plans/{run['plan_id']}").json()
        assert plan["canonical_params"]["pipeline"]["nodes"][0]["operator"] == version["id"]
        assert client.get(f"/api/tasks/{run['task_id']}").json()["state"] == "QUEUED"
        assert (
            client.post(
                f"/api/custom-operators/{'0' * 64}/runs", json={"dataset_id": dataset.id}
            ).status_code
            == 404
        )


@pytest.mark.parametrize("enabled", [False, True])
def test_configuration_when_development_enabled_discloses_warning_flag(
    db: Database,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    *,
    enabled: bool,
) -> None:
    """Web clients receive the actual explicit development override without any secrets."""
    monkeypatch.setenv("DATAKEEL_SANDBOX_ALLOW_SUBPROCESS", str(enabled).lower())
    with TestClient(create_app(db)) as client:
        config = client.get("/api/custom-operators/configuration").json()
        assert config["subprocess_enabled"] is enabled
        assert config["backend"] == get_settings().sandbox_backend
        assert set(config) == {"backend", "subprocess_enabled", "container_image"}
        assert ("UNSAFE subprocess backend enabled" in caplog.text) is enabled
