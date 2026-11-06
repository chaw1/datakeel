# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""W-E-A6/A7: precise invalidation, mode isolation and unified vector publication."""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import func, select

from datakeel.core.vector_models import VectorError
from datakeel.dataset_store.datasets import persist_files
from datakeel.dataset_store.rows import EventRow, VersionRow
from datakeel.evidence.vector_transport import FakeReply, FakeVectorTransport
from datakeel.storage.evidence_import import source_manifest
from datakeel.storage.evidence_projection import projection_hash, rebuild_evidence
from datakeel.storage.evidence_runs import extraction_report
from datakeel.storage.evidence_store import list_assertions
from datakeel.storage.task_queue import DatabaseQueue
from datakeel.storage.vector_budget import list_vector_attempts
from datakeel.storage.vector_cache import vector_cached
from datakeel.storage.vector_rows import VectorCacheRow
from datakeel.worker.runner import run_worker
from tests.evidence.vector_helpers import (
    vector_dataset,
    vector_prepare,
    vector_run,
    vector_schedule,
)

if TYPE_CHECKING:
    from pathlib import Path

    from datakeel.core.vector_models import FrozenVectorNode
    from datakeel.evidence.vector_payload import PreparedWire
    from datakeel.storage.database import Database


def _new_version(db: Database, dataset_id: str, path: Path) -> str:
    _, original = source_manifest(db, dataset_id)
    path.write_bytes(b"changed original fixture")
    changed = original[0].model_copy(update={"path": str(path)})
    files = persist_files([changed, *original[1:]])
    with db.session() as session:
        row = VersionRow(
            dataset_id=dataset_id, manifest=[file.model_dump(mode="json") for file in files]
        )
        session.add(row)
        session.commit()
        return row.id


def test_typed_input_failure_survives_all_hot_cache(db: Database, tmp_path: Path) -> None:
    """A cached invalid UTF-8 input remains failed, without producing a substitute vector."""
    dataset = vector_dataset(db, tmp_path / "inputs", (b"one", b"\xff", b"three"))
    cold = vector_run(db, dataset)
    hot = vector_run(db, dataset)
    for task in (cold, hot):
        assert task.state == "COMPLETED", task.error
        assert task.partial
        assert task.vector is not None
        assert task.vector.status == "partial_success"
        for node in task.vector.nodes:
            assert node.counts.model_dump() == {
                "input": 3,
                "eligible": 2,
                "failed": 1,
                "truncated": 0,
            }
    assert len(cold.vector.attempts) == 2
    assert hot.vector.attempts == ()
    for item in extraction_report(db, hot.id).operators:
        assert item.inputs == item.extracted + item.skipped_cached + item.failed
        assert item.extracted == 0


def test_all_failed_inputs_keep_failure_counts_without_publishing_products(
    db: Database, tmp_path: Path
) -> None:
    """Known input failures retain their counts on the failed task."""
    task = vector_run(db, vector_dataset(db, tmp_path / "inputs", (b"\xff", b"")))
    assert task.state == "FAILED"
    assert task.vector is not None
    assert task.vector.status == "failed"
    assert task.vector.attempts == ()
    assert task.vector.nodes[0].counts.model_dump() == {
        "input": 2,
        "eligible": 0,
        "failed": 2,
        "truncated": 0,
    }
    assert list_assertions(db) == []
    with db.session() as session:
        assert session.scalar(select(func.count()).select_from(VectorCacheRow)) == 0


def test_temporary_failure_is_retried_only_by_new_signed_run(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Transient outcomes are never cached; recovery reuses only the other valid peers."""
    dataset = vector_dataset(db, tmp_path / "inputs")
    original = FakeVectorTransport._respond  # noqa: SLF001  # Inject only synthetic responses.
    failing = hashlib.sha256(b"two").hexdigest()
    active = True

    def respond(self: FakeVectorTransport, node: FrozenVectorNode, wire: PreparedWire) -> FakeReply:
        return (
            FakeReply(status=503, body=b"")
            if active and wire.frozen.content_revision == failing
            else original(self, node, wire)
        )

    monkeypatch.setattr(FakeVectorTransport, "_respond", respond)
    cold = vector_run(db, dataset)
    assert cold.partial
    assert cold.vector is not None
    assert cold.vector.nodes[0].counts.failed == 1
    assert len(cold.vector.attempts) == 3
    assert any(attempt.state == "UNKNOWN" for attempt in cold.vector.attempts)
    active = False
    recovered = vector_run(db, dataset)
    assert recovered.state == "COMPLETED"
    assert recovered.vector is not None
    assert len(recovered.vector.attempts) == 1
    assert recovered.vector.nodes[0].counts.eligible == 3
    hot = vector_run(db, dataset)
    assert hot.vector is not None
    assert hot.vector.attempts == ()


def test_one_peer_revision_reembeds_only_that_peer_and_changes_global_key(
    db: Database, tmp_path: Path
) -> None:
    """Embedding identity excludes peers, while global identity binds all target revisions."""
    dataset = vector_dataset(db, tmp_path / "inputs")
    first = vector_run(db, dataset)
    old = extraction_report(db, first.id).operators[-1].vector
    version = _new_version(db, dataset, tmp_path / "changed.txt")
    task_id = vector_schedule(db, vector_prepare(db, dataset, version_id=version))
    run_worker(db, once=True)
    new = extraction_report(db, task_id).operators[-1].vector
    assert new is not None
    assert old is not None
    assert old.canonical_hash != new.canonical_hash
    assert len(list_vector_attempts(db, task_id)) == 1


def test_last_node_failure_discards_new_pending_and_keeps_history_and_charges(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An already settled embedding does not publish when the last comparison fails."""
    dataset = vector_dataset(db, tmp_path / "inputs")
    vector_run(db, dataset)
    before = list_assertions(db)
    before_hash = projection_hash(db)
    with db.session() as session:
        old_count = session.scalar(select(func.count()).select_from(VectorCacheRow))
    version = _new_version(db, dataset, tmp_path / "changed.txt")

    def fail(*args: object) -> None:
        msg = "vector_fixture_last_node_failure"
        raise VectorError(msg)

    monkeypatch.setattr("datakeel.evidence.vector_execution.direct_pairs", fail)
    task_id = vector_schedule(db, vector_prepare(db, dataset, version_id=version))
    run_worker(db, once=True)
    assert list_assertions(db) == before
    assert projection_hash(db) == before_hash
    with db.session() as session:
        assert session.scalar(select(func.count()).select_from(VectorCacheRow)) == old_count
        events = list(
            session.scalars(
                select(EventRow).where(EventRow.payload["source_ref"].as_string() == task_id)
            )
        )
        assert not any(event.payload.get("event_type") == "COMPLETE" for event in events)
    attempts = list_vector_attempts(db, task_id)
    assert len(attempts) == 1
    assert attempts[0].state == "SETTLED"


@pytest.mark.parametrize("mode", ["real", "recording"])
def test_other_mode_cache_cannot_satisfy_fake(db: Database, tmp_path: Path, mode: str) -> None:
    """Even an identical key and valid vector cannot bridge real/recording/fake namespaces."""
    dataset = vector_dataset(db, tmp_path / "inputs")
    vector_run(db, dataset)
    with db.session() as session:
        row = session.scalars(select(VectorCacheRow)).first()
        assert row is not None
        key = row.payload["key"]
        kind = row.payload["kind"]
        value = {**row.payload, "mode": mode}
        row.namespace_key = row.namespace_key.replace("fake:", mode + ":", 1)
        row.payload = value
        session.commit()
    assert vector_cached(db, key, kind) is None


def test_rebuild_replays_vectors_without_transport_and_preserves_hash(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Projection rebuild reads recorded model output only, including direct measurements."""
    dataset = vector_dataset(db, tmp_path / "inputs")
    vector_run(db, dataset)
    expected = projection_hash(db)

    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail("rebuild constructed transport")

    monkeypatch.setattr(FakeVectorTransport, "__init__", forbidden)
    assert rebuild_evidence(db).matches
    assert rebuild_evidence(db).after_hash == expected
    assert DatabaseQueue(db).claim() is None
