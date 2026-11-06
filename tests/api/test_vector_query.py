# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Read-only vector HTTP snapshots using generated sources and the real fake worker."""

import base64
from pathlib import Path

import pytest
from sqlalchemy import inspect, select

from datakeel.api.app import create_app
from datakeel.dataset_store.rows import EventRow
from datakeel.persistence.canonical import canonical_schema
from datakeel.storage import vector_cursor
from datakeel.storage.database import Database
from datakeel.storage.evidence_rows import AssertionRow
from tests.asgi_client import TestClient
from tests.evidence.test_vector_set_execution import set_pipeline
from tests.evidence.vector_helpers import vector_dataset, vector_run


def test_vector_cursor_snapshot_forgery_filters_actor_and_expiry(
    db: Database, tmp_path: Path
) -> None:
    """Continuation is bounded, non-overlapping, authenticated and tied to the exact query."""
    task = vector_run(db, vector_dataset(db, tmp_path, (b"same",) * 4))
    with TestClient(create_app(db)) as client:
        body = {"run_id": task.id, "page_size": 2}
        first = client.post("/api/evidence/vector/query", json=body)
        assert first.status_code == 200, first.text
        data = first.json()
        assert data["total"] == 6
        assert data["status"] == "current"
        assert data["report"]["status"] == "success"
        assert data["events"][0]["mode"] == "fake"
        assert all("parameters" not in e for e in data["events"])
        cursor = data["next_cursor"]
        second = client.post("/api/evidence/vector/query", json={**body, "cursor": cursor})
        assert second.status_code == 200
        assert second.json()["snapshot"] == data["snapshot"]
        assert {i["id"] for i in data["items"]}.isdisjoint(i["id"] for i in second.json()["items"])
        for change in (
            {"kind": "outlier"},
            {"page_size": 3},
            {"statuses": ["rejected"]},
            {"reference_id": "other"},
            {"cluster_id": "other"},
        ):
            invalid = client.post(
                "/api/evidence/vector/query", json={**body, "cursor": cursor, **change}
            )
            assert invalid.status_code == 422
        assert (
            client.post(
                "/api/evidence/vector/query",
                json={**body, "cursor": cursor},
                headers={"X-Datakeel-Actor": "other"},
            ).status_code
            == 422
        )
        raw = bytearray(base64.urlsafe_b64decode(cursor))
        raw[0] ^= 1
        forged = base64.urlsafe_b64encode(raw).decode()
        for token in ("garbage", forged, cursor[:-4] + "AAAA", "x" * 2049):
            assert (
                client.post(
                    "/api/evidence/vector/query", json={**body, "cursor": token}
                ).status_code
                == 422
            )


def test_vector_review_append_only_and_rerun_require_fresh_pagination(
    db: Database, tmp_path: Path
) -> None:
    """A decision or a superseding run cannot change the remainder of an existing page."""
    dataset = vector_dataset(db, tmp_path, (b"same",) * 4)
    task = vector_run(db, dataset)
    with TestClient(create_app(db)) as client:
        body = {"run_id": task.id, "page_size": 1}
        first = client.post("/api/evidence/vector/query", json=body).json()
        identifier = first["items"][0]["id"]
        with db.session() as session:
            row = session.get(AssertionRow, identifier)
            assert row
            payload = dict(row.payload)
            events = {r.event_id: dict(r.payload) for r in session.scalars(select(EventRow))}
        decision = client.post(
            "/api/evidence/assertions/decide",
            json={
                "assertion_ids": [identifier],
                "status": "accepted",
                "reason": "human review",
            },
        )
        assert decision.status_code == 200, decision.text
        assert decision.json()["status"] == "SUCCEEDED"
        assert (
            client.post(
                "/api/evidence/vector/query", json={**body, "cursor": first["next_cursor"]}
            ).status_code
            == 422
        )
        reviewed = client.post("/api/evidence/vector/query", json=body).json()
        assert reviewed["items"][0]["status"] == "accepted"
        with db.session() as session:
            row = session.get(AssertionRow, identifier)
            assert row
            assert row.payload == payload
            for key, value in events.items():
                recorded = session.get(EventRow, key)
                assert recorded
                assert recorded.payload == value
        rerun = vector_run(db, dataset)
        assert rerun.id != task.id
        assert (
            client.post(
                "/api/evidence/vector/query", json={**body, "cursor": reviewed["next_cursor"]}
            ).status_code
            == 422
        )
        old = client.post("/api/evidence/vector/query", json=body).json()
        assert old["status"] == "stale"
        assert old["items"] == []
        assert (
            client.post(
                "/api/evidence/vector/query",
                json={**body, "run_id": rerun.id, "cursor": first["next_cursor"]},
            ).status_code
            == 422
        )


@pytest.mark.parametrize(
    ("operator", "kind", "params", "measurement"),
    [
        ("evidence.semantic_cluster", "cluster", {"eps": 0.0, "min_samples": 2}, "cluster_config"),
        ("evidence.semantic_outlier", "outlier", {"eps": 0.0, "min_samples": 1}, "outlier_config"),
    ],
)
def test_vector_set_filters_and_empty_success_are_explicit(
    db: Database,
    tmp_path: Path,
    operator: str,
    kind: str,
    params: dict[str, object],
    measurement: str,
) -> None:
    """Clusters expose stable refs and members; absence of DBSCAN noise stays a valid zero."""
    dataset = vector_dataset(db, tmp_path, (b"same",) * 3)
    task = vector_run(db, dataset, set_pipeline(operator, params))
    with TestClient(create_app(db)) as client:
        body = {"run_id": task.id, "kind": kind}
        result = client.post("/api/evidence/vector/query", json=body)
        assert result.status_code == 200, result.text
        data = result.json()
        assert data["status"] == "current"
        assert data["report"]["status"] == "success"
        if kind == "cluster":
            assert len(data["items"]) == 3
            fact = data["items"][0]
            assert fact["measurement"]["type"] == measurement
            assert len(fact["measurement"]["members"]) == 3
            filtered = client.post(
                "/api/evidence/vector/query",
                json={
                    **body,
                    "cluster_id": fact["object"]["asset_id"],
                    "subject_ids": [fact["subject"]["asset_id"]],
                },
            )
            assert filtered.json()["items"] == [fact]
        else:
            assert data["items"] == []
        assert len(canonical_schema().tables) == 102
        expected_tables = 103 if db.engine.dialect.name == "sqlite" else 102
        assert len(inspect(db.engine).get_table_names()) == expected_tables


def test_vector_partial_failure_is_not_empty_success(db: Database, tmp_path: Path) -> None:
    """Input failure remains visible in report counts even if the candidate filter is empty."""
    task = vector_run(db, vector_dataset(db, tmp_path, (b"one", b"\xff", b"three")))
    with TestClient(create_app(db)) as client:
        data = client.post(
            "/api/evidence/vector/query", json={"run_id": task.id, "kind": "outlier"}
        ).json()
        assert data["items"] == []
        assert data["report"]["status"] == "partial_success"
        counts = data["report"]["nodes"][0]["counts"]
        assert counts == {"input": 3, "eligible": 2, "failed": 1, "truncated": 0}
        assert len(data["report"]["attempts"]) == 2
        assert all(a["usage"] is not None for a in data["report"]["attempts"])


def test_vector_cursor_expiry_and_page_bounds(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Expired valid signatures and unbounded HTTP pages are rejected."""
    task = vector_run(db, vector_dataset(db, tmp_path, (b"same",) * 3))
    with TestClient(create_app(db)) as client:
        body = {"run_id": task.id, "page_size": 1}
        monkeypatch.setattr(vector_cursor, "CURSOR_SECONDS", -1)
        expired = client.post("/api/evidence/vector/query", json=body).json()["next_cursor"]
        assert (
            client.post("/api/evidence/vector/query", json={**body, "cursor": expired}).status_code
            == 422
        )
        for size in (0, 201):
            assert (
                client.post(
                    "/api/evidence/vector/query", json={**body, "page_size": size}
                ).status_code
                == 422
            )
        assert (
            client.post(
                "/api/evidence/vector/query", json={**body, "dataset_id": "wrong"}
            ).status_code
            == 404
        )
