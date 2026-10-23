# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Integration regressions for concurrent publication and audit evidence."""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING

import pytest

from datakeel.api.app import create_app
from datakeel.lineage.service import all_events
from datakeel.storage import objects
from datakeel.storage.database import ShardRow, TaskRow
from datakeel.storage.datasets import import_dataset
from datakeel.storage.objects import LocalStore
from datakeel.worker.queue import DatabaseQueue
from datakeel.worker.runner import execute
from tests.asgi_client import TestClient

if TYPE_CHECKING:
    from pathlib import Path

    from pydantic import JsonValue

    from datakeel.core.models import FileItem, LineageEvent
    from datakeel.storage.database import Database
    from datakeel.storage.task_models import Lease


def import_text(db: Database, tmp_path: Path, metadata: dict[str, JsonValue] | None = None) -> str:
    """Provide the import text test fixture."""
    source = tmp_path / "source.txt"
    source.write_text("A generated example for integration checks.")
    with db.session() as session:
        dataset = import_dataset(session, "review-example", [source], metadata=metadata)
        session.commit()
        return dataset.id


def test_parallel_branches_keep_their_declared_lineage(db: Database, tmp_path: Path) -> None:
    """Verify parallel branches keep their declared lineage."""
    identifier = import_text(db, tmp_path)
    definition = {
        "nodes": [
            {"id": "left", "operator": "file.empty_check", "inputs": {"files": "$input.files"}},
            {"id": "right", "operator": "file.corrupt_check", "inputs": {"files": "$input.files"}},
            {"id": "condition", "kind": "condition", "inputs": {"files": "right.files"}},
            {"id": "after", "operator": "file.dedup", "inputs": {"files": "condition.true"}},
        ],
        "outputs": ["left.files", "after.files"],
    }
    queue = DatabaseQueue(db)
    task_id = queue.submit(identifier, "branches", definition)
    lease = queue.claim()
    assert lease is not None
    assert execute(queue, lease)
    with db.session() as session:
        events = {
            event.operator: event for event in all_events(session) if event.source_ref == task_id
        }
    for operator in ("file.empty_check", "file.corrupt_check"):
        assert [asset.asset_id for asset in events[operator].inputs] == [identifier]
    assert [asset.asset_id for asset in events["file.dedup"].inputs] == [f"{lease.shard_id}:right"]


def test_reaper_rechecks_a_heartbeat_renewed_before_terminal_lock(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify reaper rechecks a heartbeat renewed before terminal lock."""
    identifier = import_text(db, tmp_path)
    queue = DatabaseQueue(db, lease_seconds=0.01, max_attempts=1)
    task_id = queue.submit(identifier, "renew-during-reap")
    lease = queue.claim()
    assert lease is not None
    with db.session() as session:
        shard = session.get(ShardRow, lease.shard_id)
        assert shard is not None
        shard.heartbeat_at = time.time() - 60
        session.commit()
    finish = queue.finish
    renewed = []

    def renew_then_finish(
        claimed: Lease,
        outputs: list[FileItem],
        events: list[LineageEvent],
        error: str | None = None,
        expired_before: float | None = None,
    ) -> bool:
        """Provide the renew then finish test fixture."""
        renewed.append(queue.heartbeat(lease))
        return finish(claimed, outputs, events, error, expired_before)

    monkeypatch.setattr(queue, "finish", renew_then_finish)
    assert queue.reap() == 0
    assert renewed == [True]
    with db.session() as session:
        task = session.get(TaskRow, task_id)
        shard = session.get(ShardRow, lease.shard_id)
        assert task is not None
        assert task.state != "FAILED"
        assert shard is not None
        assert shard.state == "RUNNING"
        assert shard.lease_owner == lease.owner
    assert finish(lease, [], [])


@pytest.mark.parametrize(("before", "after"), [(1, True), ({"enabled": 1}, {"enabled": True})])
def test_metadata_audit_records_json_type_changes(
    db: Database, tmp_path: Path, before: JsonValue, after: JsonValue
) -> None:
    """Verify metadata audit records json type changes."""
    identifier = import_text(db, tmp_path, {"flag": before})
    with TestClient(create_app(db)) as client:
        root = f"/api/datasets/{identifier}"
        saved = client.put(
            root + "/metadata", json={"values": {"flag": after}, "reason": "Correct field type"}
        )
        assert saved.status_code == 200, saved.text
        changes = client.get(root + "/metadata/changes").json()
        assert len(changes) == 1
        assert changes[0]["field"] == "flag"
        assert changes[0]["reason"] == "Correct field type"
        assert type(changes[0]["before"]) is type(before)
        assert type(changes[0]["after"]) is type(after)


def test_concurrent_same_content_puts_use_independent_temporary_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify concurrent same content puts use independent temporary files."""
    source = tmp_path / "source.txt"
    source.write_bytes(b"identical content")
    store = LocalStore(tmp_path / "objects")
    barrier = threading.Barrier(2, timeout=5)
    original_copy = objects.shutil.copyfile
    temporary_paths = []

    def copy_before_commit(source: Path, temporary: Path) -> Path:
        """Provide the copy before commit test fixture."""
        result = original_copy(source, temporary)
        temporary_paths.append(temporary)
        barrier.wait()
        return result

    monkeypatch.setattr(objects.shutil, "copyfile", copy_before_commit)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: store.put(source, "aa/shared.txt"), range(2)))
    assert results == ["aa/shared.txt", "aa/shared.txt"]
    assert len(set(temporary_paths)) == 2
    assert store.materialize("aa/shared.txt").read_bytes() == source.read_bytes()
    assert all(not path.exists() for path in temporary_paths)
