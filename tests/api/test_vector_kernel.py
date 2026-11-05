# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Existing HTTP routes retain typed fake status and refuse unsigned queue bypasses."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi.testclient import TestClient

from datakeel.api.app import create_app
from datakeel.worker.runner import run_worker
from tests.evidence.vector_helpers import vector_dataset, vector_pipeline

if TYPE_CHECKING:
    from pathlib import Path

    from datakeel.storage.database import Database


def test_vector_existing_http_routes_expose_status_and_typed_refusal(
    db: Database, tmp_path: Path
) -> None:
    """Unsigned queue calls fail; signed work exposes actual fake attempts and node counts."""
    dataset = vector_dataset(db, tmp_path / "inputs")
    body = {"dataset_id": dataset, "pipeline": vector_pipeline().model_dump(mode="json")}
    with TestClient(create_app(db)) as client:
        rejected = client.post("/api/tasks", json=body)
        assert rejected.status_code == 422
        assert rejected.json()["reason"] == "vector_direct_queue_refused"
        prepared = client.post("/api/actions/run_pipeline/prepare", json=body)
        assert prepared.status_code == 200
        plan = prepared.json()
        assert plan["external"]
        signed = client.post(
            f"/api/approvals/{plan['id']}",
            json={"approve": True, "plan_digest": plan["plan_digest"]},
        )
        assert signed.status_code == 200
        queued = client.post(
            f"/api/actions/{plan['id']}/execute", json={"plan_digest": plan["plan_digest"]}
        )
        assert queued.status_code == 200
        run_worker(db, once=True)
        task = client.get(f"/api/tasks/{queued.json()['task_id']}").json()
        assert task["vector"]["status"] == "success"
        assert task["vector"]["nodes"][0]["counts"]["input"] == 3
        assert len(task["vector"]["attempts"]) == 3
        action = next(
            item
            for item in client.get("/api/actions/runs").json()
            if item["id"] == queued.json()["id"]
        )
        assert action["vector"]["status"] == "success"
