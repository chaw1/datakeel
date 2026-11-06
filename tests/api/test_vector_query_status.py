# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Failed, pending and insufficient vector runs never become successful empty coverage."""

from pathlib import Path

from sqlalchemy import inspect, select

from datakeel.api.app import create_app
from datakeel.dataset_store.rows import EventRow
from datakeel.storage.database import Database
from datakeel.storage.evidence_rows import AssertionDecisionRow, AssertionRow
from datakeel.storage.vector_rows import VectorAttemptRow, VectorCacheRow
from tests.asgi_client import TestClient
from tests.evidence.test_vector_set_execution import set_pipeline
from tests.evidence.vector_helpers import (
    vector_dataset,
    vector_prepare,
    vector_run,
    vector_schedule,
)


def test_vector_query_failed_reference_and_pending_status_are_explicit(
    db: Database, tmp_path: Path
) -> None:
    """An empty R is a failed run and pending work does not masquerade as all covered."""
    dataset = vector_dataset(db, tmp_path)
    pipeline = set_pipeline(
        "evidence.coverage_gap",
        {
            "reference": {"dataset_id": dataset, "filters": [{"field": "id", "value": "missing"}]},
        },
    )
    pending = vector_schedule(db, vector_prepare(db, dataset, pipeline))
    with TestClient(create_app(db)) as client:
        body = {"run_id": pending, "kind": "coverage"}
        value = client.post("/api/evidence/vector/query", json=body).json()
        assert value["status"] == "unpublished"
        assert value["report"]["status"] == "pending"
        assert value["items"] == []
    from datakeel.worker.runner import run_worker  # noqa: PLC0415

    run_worker(db, once=True)
    with TestClient(create_app(db)) as client:
        value = client.post("/api/evidence/vector/query", json=body).json()
        assert value["items"] == []
        assert value["report"]["status"] == "failed"
        assert value["report"]["reason"] == "vector_reference_empty"
        assert value["status"] == "unpublished"
        assert value["report"]["attempts"]


def test_vector_query_insufficient_noise_and_query_has_no_writes(
    db: Database, tmp_path: Path
) -> None:
    """Noise requires sufficient density input and repeated reads never append facts or usage."""
    dataset = vector_dataset(db, tmp_path, (b"same",))
    task = vector_run(db, dataset, set_pipeline("evidence.semantic_outlier", {"min_samples": 2}))
    models = (AssertionRow, AssertionDecisionRow, EventRow, VectorCacheRow, VectorAttemptRow)
    with db.session() as session:
        before = [
            tuple(str(r) for r in session.execute(select(model.__table__))) for model in models
        ]
    with TestClient(create_app(db)) as client:
        for _ in range(2):
            value = client.post(
                "/api/evidence/vector/query", json={"run_id": task.id, "kind": "outlier"}
            ).json()
            assert value["items"] == []
            assert value["report"]["status"] == "insufficient"
            assert value["report"]["reason"] == "vector_insufficient_samples"
            assert value["report"]["nodes"][1]["counts"]["input"] == 1
    with db.session() as session:
        after = [
            tuple(str(r) for r in session.execute(select(model.__table__))) for model in models
        ]
    assert after == before
    expected_tables = 103 if db.engine.dialect.name == "sqlite" else 102
    assert len(inspect(db.engine).get_table_names()) == expected_tables


def test_vector_query_old_zero_result_is_stale_after_rerun(db: Database, tmp_path: Path) -> None:
    """Global publication identity protects empty results as well as candidates."""
    dataset = vector_dataset(db, tmp_path, (b"same",) * 2)
    pipeline = set_pipeline("evidence.semantic_outlier", {"eps": 0.0, "min_samples": 2})
    first = vector_run(db, dataset, pipeline)
    with TestClient(create_app(db)) as client:
        body = {"run_id": first.id, "kind": "outlier"}
        before = client.post("/api/evidence/vector/query", json=body).json()
        assert before["status"] == "current"
        assert before["items"] == []
        second = vector_run(db, dataset, pipeline)
        after = client.post("/api/evidence/vector/query", json=body).json()
        assert after["status"] == "stale"
        assert before["snapshot"] != after["snapshot"]
        current = client.post(
            "/api/evidence/vector/query", json={**body, "run_id": second.id}
        ).json()
        assert current["status"] == "current"
