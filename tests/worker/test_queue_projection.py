# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Queue bookkeeping projects small columns instead of repeatedly decoding manifests."""

from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import event, select

from datakeel.core.errors import NotFoundError
from datakeel.storage.database import DatasetRow, VersionRow
from datakeel.worker.queue import DatabaseQueue
from tests.worker.test_queue import seed

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

    from sqlalchemy.engine import Connection

    from datakeel.storage.database import Database


@contextmanager
def statements(database: Database) -> Iterator[list[str]]:
    """Record query projections without depending on stack-specific SQL parameters."""
    recorded: list[str] = []

    def record(_connection: Connection, _cursor: object, statement: str, *_args: object) -> None:
        if statement.startswith("SELECT"):
            recorded.append(statement)

    event.listen(database.engine, "before_cursor_execute", record)
    try:
        yield recorded
    finally:
        event.remove(database.engine, "before_cursor_execute", record)


def test_claim_reads_source_identity_without_decoding_its_manifest(
    db: Database, tmp_path: Path
) -> None:
    """Source selection retains the oldest version while returning only its stable ID."""
    identifier = seed(db, tmp_path)
    with db.session() as session:
        original = session.scalar(select(VersionRow).where(VersionRow.dataset_id == identifier))
        assert original is not None
        original_id = original.id
        session.add(VersionRow(dataset_id=identifier, manifest=[]))
        session.commit()
    queue = DatabaseQueue(db)
    queue.submit(identifier, "project-source", shards=2)
    with statements(db) as recorded:
        lease = queue.claim()
    assert lease is not None
    assert lease.input_version_id == original_id
    source = [
        statement.partition("FROM")[0] for statement in recorded if "FROM versions" in statement
    ]
    assert source
    assert all("versions.manifest" not in statement for statement in source)


def test_heartbeat_and_partial_finish_do_not_read_any_manifest(
    db: Database, tmp_path: Path
) -> None:
    """A small lease update never loads its shard input or any sibling JSON."""
    queue = DatabaseQueue(db)
    queue.submit(seed(db, tmp_path), "project-partial", shards=2)
    lease = queue.claim()
    assert lease is not None
    with statements(db) as recorded:
        assert queue.heartbeat(lease)
        assert queue.finish(lease, lease.inputs, [])
    selected = [statement.partition("FROM")[0] for statement in recorded]
    assert all("task_shards.inputs" not in statement for statement in selected)
    assert all("task_shards.outputs" not in statement for statement in selected)


def test_last_finish_reads_only_outputs_and_preserves_ordinal_order(
    db: Database, tmp_path: Path
) -> None:
    """Only the terminal shard merges output JSON, independent of completion order."""
    queue = DatabaseQueue(db)
    task_id = queue.submit(seed(db, tmp_path), "project-final", shards=2)
    first, second = queue.claim(), queue.claim()
    assert first is not None
    assert second is not None
    assert queue.finish(second, second.inputs, [])
    with statements(db) as recorded:
        assert queue.finish(first, first.inputs, [])
    shard_columns = [statement.partition("FROM")[0] for statement in recorded]
    assert all("task_shards.inputs" not in statement for statement in shard_columns)
    assert sum("task_shards.outputs" in statement for statement in shard_columns) == 1
    with db.session() as session:
        manifest = session.scalar(select(VersionRow.manifest).where(VersionRow.task_id == task_id))
    assert manifest is not None
    assert [value["id"] for value in manifest] == [
        item.id for item in [*first.inputs, *second.inputs]
    ]


def test_claim_without_source_manifest_reports_not_found(db: Database) -> None:
    """An inconsistent legacy dataset cannot invent a version identity."""
    with db.session() as session:
        session.add(DatasetRow(id="without-version", name="Generated", files=[]))
        session.commit()
    queue = DatabaseQueue(db)
    queue.submit("without-version", "missing-source")
    with pytest.raises(NotFoundError, match="Task source manifest version is missing"):
        queue.claim()
