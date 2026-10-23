# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Workflow HTTP starts, signed recovery and durable timeline projections."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from datakeel.actions.service import get_plan, list_runs
from datakeel.api.app import create_app
from datakeel.core.workflow_models import WorkflowEvent, WorkflowRun
from tests.asgi_client import TestClient
from tests.workflows.conftest import create_dataset, worker_hooks

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

    from httpx2 import Response

    from datakeel.storage.database import Database


@pytest.fixture
def workflow_client(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[tuple[TestClient, str]]:
    """Expose only freshly generated inputs and an injectable local worker."""
    monkeypatch.delenv("DATAKEEL_LLM_URL", raising=False)
    dataset = create_dataset(db, tmp_path / "workflow-api")
    app = create_app(db)
    app.state.workflow_hooks = worker_hooks(db)
    with TestClient(app) as client:
        yield client, dataset.id


def decode(response: Response) -> list[WorkflowEvent]:
    """Validate each actual SSE payload through the public boundary model."""
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/event-stream")
    result = [
        WorkflowEvent.model_validate_json(line.removeprefix("data: "))
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]
    assert result[-1].event == "done"
    return result


def test_definitions_and_missing_requests_preserve_typed_errors(
    workflow_client: tuple[TestClient, str],
) -> None:
    """A valid key and required schema inputs are necessary before any execution is created."""
    client, dataset_id = workflow_client
    definitions = client.get("/api/workflows").json()
    assert {item["id"] for item in definitions} == {
        "dataset-health",
        "metric-change",
        "low-quality-cleanup",
    }
    assert client.get("/api/workflows/dataset-health").json()["inputs"]["dataset_id"]["required"]
    assert client.get("/api/workflows/unknown").status_code == 404
    for payload in ({"inputs": {"dataset_id": dataset_id}}, {"idempotency_key": "empty"}):
        assert client.post("/api/workflows/dataset-health/runs", json=payload).status_code == 422
    assert client.get("/api/workflows/runs").json() == []
    assert client.get("/api/workflows/runs/missing").status_code == 404
    assert client.get("/api/workflows/runs/missing/audit").status_code == 404
    assert (
        client.post(
            "/api/workflows/runs/missing/resume",
            json={"plan_id": "missing", "idempotency_key": "missing"},
        ).status_code
        == 404
    )


def test_start_runs_real_pipeline_and_replays_one_identity(
    workflow_client: tuple[TestClient, str],
) -> None:
    """The real wait node observes worker completion and exposes quality in the timeline."""
    client, dataset_id = workflow_client
    request = {"inputs": {"dataset_id": dataset_id}, "idempotency_key": "health"}
    first = decode(client.post("/api/workflows/dataset-health/runs", json=request))
    run = first[-1].run
    assert run.status == "SUCCEEDED"
    quality = next(step.output for step in run.steps if step.id == "quality")
    assert isinstance(quality, dict)
    assert isinstance(quality["data"], dict)
    assert isinstance(quality["data"]["total"], int | float)
    assert decode(client.post("/api/workflows/dataset-health/runs", json=request))[-1].run == run
    assert WorkflowRun.model_validate(client.get(f"/api/workflows/runs/{run.id}").json()) == run
    assert [item["id"] for item in client.get("/api/workflows/runs").json()] == [run.id]
    assert client.post("/api/workflows/low-quality-cleanup/runs", json=request).status_code == 409


def test_cleanup_http_requires_real_approval_then_explicit_resume(
    db: Database, workflow_client: tuple[TestClient, str]
) -> None:
    """Neither a caller-supplied approval flag nor an unsigned resume can delete files."""
    client, dataset_id = workflow_client
    started = decode(
        client.post(
            "/api/workflows/low-quality-cleanup/runs",
            json={
                "inputs": {"dataset_id": dataset_id, "quality_max": 0},
                "idempotency_key": "cleanup",
            },
        )
    )[-1].run
    assert started.status == "PAUSED"
    assert started.pending_plan_id is not None
    plan = get_plan(db, started.pending_plan_id)
    assert plan.agent_id == "datakeel-workflow"
    assert plan.session_id == started.id
    url = f"/api/workflows/runs/{started.id}/resume"
    payload = {"plan_id": plan.id, "idempotency_key": "resume"}
    assert client.post(url, json={**payload, "approve": True}).status_code == 422
    denied = client.post(url, json=payload)
    assert denied.status_code == 403
    audit = client.get(f"/api/workflows/runs/{started.id}/audit").json()
    assert [entry["kind"] for entry in audit] == ["RESUME_DENIED"]
    assert (
        client.post(
            f"/api/approvals/{plan.id}", json={"approve": True, "plan_digest": plan.plan_digest}
        ).status_code
        == 200
    )
    assert client.get(f"/api/workflows/runs/{started.id}").json()["status"] == "PAUSED"
    finished = decode(client.post(url, json=payload))[-1].run
    assert finished.status == "SUCCEEDED"
    assert decode(client.post(url, json=payload))[-1].run == finished
    assert len([run for run in list_runs(db) if run.plan_id == plan.id]) == 1
    assert client.post(url, json={**payload, "plan_id": "changed"}).status_code == 409


def test_workflow_openapi_has_one_resource_prefix(workflow_client: tuple[TestClient, str]) -> None:
    """Document SSE schemas and explicit idempotency without duplicate resource prefixes."""
    client, _ = workflow_client
    schema = client.get("/api/openapi.json").json()
    assert "/api/workflows/runs/{run_id}/resume" in schema["paths"]
    event = schema["components"]["schemas"]["WorkflowEvent"]
    assert event["properties"]["event"]["enum"] == ["run", "step", "done"]
    assert schema["components"]["schemas"]["WorkflowStart"]["required"] == ["idempotency_key"]
