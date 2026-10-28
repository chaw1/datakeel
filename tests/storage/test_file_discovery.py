# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Rebuildable file discovery remains transactionally aligned with version facts."""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import event, inspect, select, text

from datakeel.core.models import FileItem
from datakeel.core.search_models import SearchQuery
from datakeel.storage.database import DatasetRow, VersionRow
from datakeel.storage.file_discovery import (
    FileDiscoveryCheckpointRow,
    FileDiscoveryRow,
    begin_file_read,
    rebuild_file_discovery,
    requires_python_files,
)
from datakeel.storage.file_state import FileStateRow
from datakeel.storage.search_sources import file_results

if TYPE_CHECKING:
    from pydantic import JsonValue
    from sqlalchemy.engine import Connection

    from datakeel.storage.database import Database


def _file(identifier: str = "file", name: str = "file.txt") -> dict[str, JsonValue]:
    return FileItem(id=identifier, filename=name, path="", size=1).model_dump(mode="json")


def _dataset(database: Database) -> None:
    with database.session() as session:
        session.add(DatasetRow(id="fixture", name="Generated discovery", files=[]))
        session.commit()


def _version(database: Database, identifier: str, created: float, manifest: JsonValue) -> None:
    with database.engine.begin() as connection:
        connection.execute(
            VersionRow.__table__.insert().values(
                id=identifier, dataset_id="fixture", created_at=created, manifest=manifest
            )
        )


def _entries(database: Database) -> list[tuple[str, str, str, float]]:
    with database.session() as session:
        return [
            tuple(row)
            for row in session.execute(
                select(
                    FileDiscoveryRow.file_id,
                    FileDiscoveryRow.version_id,
                    FileDiscoveryRow.name,
                    FileDiscoveryRow.created_at,
                ).order_by(
                    FileDiscoveryRow.file_id,
                    FileDiscoveryRow.created_at,
                    FileDiscoveryRow.version_id,
                )
            )
        ]


def test_fresh_projection_identity_indexes_and_cascading_foreign_keys(db: Database) -> None:
    """Only bounded surrogate and existing ownership keys enter B-tree indexes."""
    inspector = inspect(db.engine)
    assert inspector.get_pk_constraint("file_discovery")["constrained_columns"] == ["id"]
    indexes = inspector.get_indexes("file_discovery")
    assert {tuple(index["column_names"]) for index in indexes} == {
        ("dataset_id",),
        ("version_id",),
    }
    foreign_keys = inspector.get_foreign_keys("file_discovery")
    assert {item["referred_table"] for item in foreign_keys} == {"datasets", "versions"}
    assert all(item["options"]["ondelete"] == "CASCADE" for item in foreign_keys)
    assert all(item["options"]["onupdate"] == "CASCADE" for item in foreign_keys)
    if not db.sqlite:
        with db.engine.connect() as connection:
            columns = connection.execute(
                text(
                    "SELECT a.attname, c.collname FROM pg_attribute a "
                    "JOIN pg_class t ON t.oid = a.attrelid "
                    "JOIN pg_namespace n ON n.oid = t.relnamespace "
                    "JOIN pg_collation c ON c.oid = a.attcollation "
                    "WHERE n.nspname = current_schema() AND t.relname = 'file_discovery' "
                    "AND a.attname IN ('file_id', 'version_id')"
                )
            ).all()
        assert sorted(tuple(row) for row in columns) == [("file_id", "C"), ("version_id", "C")]


def test_legacy_upgrade_backfills_once_and_rebuild_is_explicit(unmigrated_db: Database) -> None:
    """Existing manifests are indexed once; repeated startup cannot rescan or rewrite them."""
    database = unmigrated_db
    with database.engine.begin() as connection:
        DatasetRow.__table__.create(connection)
        VersionRow.__table__.create(connection)
    _dataset(database)
    _version(database, "later", 20, [_file(name="later.txt")])
    _version(database, "earlier", 10, [_file(name="earlier.txt")])
    database.migrate()
    expected = [("file", "earlier", "earlier.txt", 10), ("file", "later", "later.txt", 20)]
    assert _entries(database) == expected
    statements: list[str] = []

    def record(_connection: Connection, _cursor: object, statement: str, *_args: object) -> None:
        statements.append(statement.strip())

    event.listen(database.engine, "before_cursor_execute", record)
    try:
        database.migrate()
    finally:
        event.remove(database.engine, "before_cursor_execute", record)
    assert not any(
        statement.startswith(("DELETE FROM file_discovery", "INSERT INTO file_discovery"))
        for statement in statements
    )
    assert not any(
        statement.startswith(("CREATE", "DROP"))
        and any(
            name in statement
            for name in (
                "datakeel_file_discovery_",
                "datakeel_discovery_text",
                "datakeel_file_python_",
            )
        )
        for statement in statements
    )
    with database.engine.begin() as connection:
        connection.execute(text("DELETE FROM file_discovery"))
    with database.engine.begin() as connection:
        rebuild_file_discovery(connection, sqlite=database.sqlite)
    assert _entries(database) == expected


def test_versions_keep_earliest_order_ties_and_first_duplicate_occurrence(db: Database) -> None:
    """The narrow index retains enough facts to choose the original earliest identity."""
    _dataset(db)
    _version(db, "z", 10, [_file(name="tie-later-id.txt")])
    _version(db, "a", 10, [_file(name="first.txt"), _file(name="duplicate.txt")])
    _version(db, "oldest", 5, [_file(name="oldest.txt")])
    _version(db, "newest", 30, [_file(name="newest.txt")])
    assert _entries(db) == [
        ("file", "oldest", "oldest.txt", 5),
        ("file", "a", "first.txt", 10),
        ("file", "z", "tie-later-id.txt", 10),
        ("file", "newest", "newest.txt", 30),
    ]


def _long_id(length: int) -> str:
    return "".join(sha256(str(index).encode()).hexdigest() for index in range(length // 64 + 1))[
        :length
    ]


@pytest.mark.parametrize(("file_length", "version_length"), [(5000, 10), (500, 2500)])
def test_long_legal_identities_remain_writable_and_discoverable(
    db: Database, file_length: int, version_length: int
) -> None:
    """Nested JSON identities gain neither individual nor combined B-tree key limits."""
    _dataset(db)
    identifier, version = _long_id(file_length), _long_id(version_length)
    _version(db, version, 10, [_file(identifier, "long.txt"), _file(identifier, "duplicate.txt")])
    expected = [(identifier, version, "long.txt", 10)]
    assert _entries(db) == expected
    with db.session() as session:
        assert [(item.id, item.name) for item in file_results(session, SearchQuery(q="long"))] == [
            (identifier, "long.txt")
        ]
    with db.engine.begin() as connection:
        rebuild_file_discovery(connection, sqlite=db.sqlite)
    assert _entries(db) == expected


def test_manifest_update_identity_update_and_delete_touch_only_owned_version(db: Database) -> None:
    """Mutable unsealed versions replace their own rows and leave other versions intact."""
    _dataset(db)
    _version(db, "old", 10, [_file(name="old.txt")])
    _version(db, "new", 20, [_file(name="new.txt")])
    with db.session() as session:
        version = session.get(VersionRow, "old")
        assert version is not None
        version.id, version.created_at = "renamed", 30
        version.manifest = [_file("other", "changed.txt")]
        session.commit()
    assert _entries(db) == [
        ("file", "new", "new.txt", 20),
        ("other", "renamed", "changed.txt", 30),
    ]
    with db.session() as session:
        version = session.get(VersionRow, "new")
        assert version is not None
        session.delete(version)
        session.commit()
    assert _entries(db) == [("other", "renamed", "changed.txt", 30)]


def test_delete_earliest_promotes_remaining_version_without_global_rebuild(db: Database) -> None:
    """Removing one fact version leaves its later public navigation candidate available."""
    _dataset(db)
    _version(db, "first", 10, [_file(name="first.txt")])
    _version(db, "last", 20, [_file(name="last.txt")])
    with db.engine.begin() as connection:
        connection.execute(text("DELETE FROM versions WHERE id = 'first'"))
    assert _entries(db) == [("file", "last", "last.txt", 20)]


def test_version_rollback_removes_its_index_rows_in_the_same_transaction(db: Database) -> None:
    """Projection writes cannot escape the transaction that publishes the source version."""
    _dataset(db)
    with db.session() as session:
        session.add(VersionRow(id="rolled-back", dataset_id="fixture", manifest=[_file()]))
        session.flush()
        assert session.scalar(select(FileDiscoveryRow.file_id)) == "file"
        session.rollback()
    assert _entries(db) == []


@pytest.mark.parametrize("manifest", [None, "primitive", 12, {"id": "file", "filename": "f"}])
def test_non_array_manifest_does_not_gain_a_write_time_constraint(
    db: Database, manifest: JsonValue
) -> None:
    """Old JSON values can still be written even when they cannot support discovery."""
    _dataset(db)
    _version(db, "non-array", 10, manifest)
    assert _entries(db) == []


def test_invalid_entries_are_skipped_and_public_unicode_is_preserved(db: Database) -> None:
    """String primitives must never reach SQLite JSON extraction or become discovery IDs."""
    _dataset(db)
    _version(
        db,
        "mixed",
        10,
        [
            "primitive",
            17,
            None,
            [],
            {},
            {"id": "missing-name"},
            {"id": 12, "filename": "number-id"},
            {"id": "wrong-name", "filename": False},
            _file("unicode", "e\u0301-🙂.txt"),
            _file("good", "正常.txt"),
        ],
    )
    assert _entries(db) == [
        ("good", "mixed", "正常.txt", 10),
        ("unicode", "mixed", "e\u0301-🙂.txt", 10),
    ]


def test_invalid_encoded_json_keeps_existing_backend_write_semantics(db: Database) -> None:
    """SQLite accepts raw malformed JSON; PostgreSQL keeps accepting escaped JSON strings."""
    _dataset(db)
    if db.sqlite:
        with db.engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO versions (id, dataset_id, created_at, manifest) "
                    "VALUES ('malformed', 'fixture', 10, :manifest)"
                ),
                {"manifest": "{not-json"},
            )
    else:
        _version(
            db,
            "escaped",
            10,
            [
                _file("bad-null\x00", "name.txt"),
                _file("bad-surrogate", "\ud800.txt"),
                _file("valid", "valid.txt"),
            ],
        )
        assert _entries(db) == [("valid", "escaped", "valid.txt", 10)]


def test_mutable_status_is_joined_live_and_never_copied_into_index(db: Database) -> None:
    """Quarantine/deletion state changes navigation status without rewriting public names."""
    _dataset(db)
    _version(db, "version", 10, [_file()])
    before = _entries(db)
    with db.session() as session:
        session.add(FileStateRow(dataset_id="fixture", file_id="file", deleted=True, revision=1))
        session.commit()
    assert _entries(db) == before
    assert set(FileDiscoveryRow.__table__.columns.keys()) == {
        "id",
        "file_id",
        "name",
        "dataset_id",
        "version_id",
        "created_at",
    }
    with db.session() as session:
        results = list(file_results(session, SearchQuery(q="file")))
    assert [(item.id, item.status) for item in results] == [("file", "deleted")]


def _wait_for_owned_backend_lock(database: Database, process_id: int) -> None:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        with database.engine.connect() as connection:
            waiting = connection.scalar(
                text("SELECT wait_event_type FROM pg_stat_activity WHERE pid = :pid"),
                {"pid": process_id},
            )
        if waiting == "Lock":
            return
        time.sleep(0.01)
    msg = "Owned worker backend did not reach its expected dataset foreign-key wait"
    raise AssertionError(msg)


def _background_insert(
    database: Database, started: threading.Event, process_ids: list[int]
) -> None:
    with database.session() as session:
        if not database.sqlite:
            process_id = session.scalar(text("SELECT pg_backend_pid()"))
            assert isinstance(process_id, int)
            process_ids.append(process_id)
        started.set()
        session.add(
            VersionRow(id="worker", dataset_id="fixture", manifest=[_file()], created_at=20)
        )
        session.commit()


def test_controlled_dataset_lock_and_worker_version_insert_do_not_deadlock(db: Database) -> None:
    """A worker cannot take a discovery lock before waiting on the API's dataset row."""
    _dataset(db)
    dataset_locked, worker_started = threading.Event(), threading.Event()
    worker_process: list[int] = []

    def controlled() -> None:
        with db.session() as session:
            db.lock_writes(session)
            session.scalar(select(DatasetRow).where(DatasetRow.id == "fixture").with_for_update())
            dataset_locked.set()
            assert worker_started.wait(timeout=5)
            if not db.sqlite:
                _wait_for_owned_backend_lock(db, worker_process[0])
            session.add(
                VersionRow(id="controlled", dataset_id="fixture", manifest=[_file()], created_at=10)
            )
            session.commit()

    def worker() -> None:
        assert dataset_locked.wait(timeout=5)
        _background_insert(db, worker_started, worker_process)

    with ThreadPoolExecutor(max_workers=2) as pool:
        api, background = pool.submit(controlled), pool.submit(worker)
        api.result(timeout=15)
        background.result(timeout=15)
    assert _entries(db) == [
        ("file", "controlled", "file.txt", 10),
        ("file", "worker", "file.txt", 20),
    ]


def test_repeated_startup_cannot_block_controlled_and_worker_version_writers(db: Database) -> None:
    """An installed index needs no version-trigger DDL while its worker awaits an API lock."""
    _dataset(db)
    started = threading.Event()
    process_ids: list[int] = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        with db.session() as session:
            db.lock_writes(session)
            session.scalar(select(DatasetRow).where(DatasetRow.id == "fixture").with_for_update())
            background = pool.submit(_background_insert, db, started, process_ids)
            assert started.wait(timeout=5)
            if not db.sqlite:
                _wait_for_owned_backend_lock(db, process_ids[0])
            migration = pool.submit(db.migrate)
            if not db.sqlite:
                migration.result(timeout=5)
            session.add(
                VersionRow(id="controlled", dataset_id="fixture", manifest=[_file()], created_at=10)
            )
            session.commit()
        background.result(timeout=15)
        migration.result(timeout=15)
    assert _entries(db) == [
        ("file", "controlled", "file.txt", 10),
        ("file", "worker", "file.txt", 20),
    ]


def _needs_python(database: Database) -> bool:
    with database.session() as session:
        return requires_python_files(session)


def test_file_read_snapshot_requires_an_unused_transaction(db: Database) -> None:
    """A fresh reader gets a stable snapshot without changing an existing caller transaction."""
    with db.session() as session:
        assert begin_file_read(session)
        assert session.in_transaction()
        if not db.sqlite:
            assert session.scalar(text("SHOW transaction_isolation")) == "repeatable read"
        assert not begin_file_read(session)
    with db.session() as session:
        assert session.scalar(text("SELECT 1")) == 1
        assert not begin_file_read(session)


@pytest.mark.parametrize("source", ["dataset", "version"])
@pytest.mark.parametrize("operation", ["insert", "update"])
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("id", "file\x00suffix"),
        ("filename", "file\x00suffix.txt"),
        ("metadata", {"control": "\x00"}),
        ("modality", "te\x00xt"),
        ("metadata", {"surrogate": "\ud800"}),
        ("metadata", {"emoji": "🙂"}),
        ("metadata", {"literal": r"\u0000"}),
    ],
    ids=["id", "name", "metadata", "modality", "surrogate", "emoji", "literal-escape"],
)
def test_unsafe_json_writes_set_sticky_python_marker(
    db: Database, source: str, operation: str, field: str, value: JsonValue
) -> None:
    """Inspect the complete source JSON, including fields absent from the narrow index."""
    raw = _file()
    raw[field] = value
    assert not _needs_python(db)
    if source == "dataset" and operation == "insert":
        with db.session() as session:
            session.add(DatasetRow(id="fixture", name="Generated", files=[raw]))
            session.commit()
    else:
        _dataset(db)
        if source == "dataset":
            with db.session() as session:
                dataset = session.get(DatasetRow, "fixture")
                assert dataset is not None
                dataset.files = [raw]
                session.commit()
        else:
            _version(db, "source", 10, [_file()] if operation == "update" else [raw])
            if operation == "update":
                with db.session() as session:
                    version = session.get(VersionRow, "source")
                    assert version is not None
                    version.manifest = [raw]
                    session.commit()
    assert _needs_python(db)


@pytest.mark.parametrize("source", ["dataset", "version"])
def test_python_marker_rolls_back_with_its_fact_write(db: Database, source: str) -> None:
    """A transaction cannot leak a global slow-path decision after its fact write rolls back."""
    _dataset(db)
    raw = _file()
    raw["metadata"] = {"control": "\x00"}
    with db.session() as session:
        if source == "dataset":
            dataset = session.get(DatasetRow, "fixture")
            assert dataset is not None
            dataset.files = [raw]
        else:
            session.add(VersionRow(id="unsafe", dataset_id="fixture", manifest=[raw]))
        session.flush()
        assert requires_python_files(session)
        session.rollback()
    assert not _needs_python(db)


@pytest.mark.parametrize("source", ["dataset", "version"])
def test_deleted_unsafe_sources_stay_marked_until_explicit_rebuild(
    db: Database, source: str
) -> None:
    """Only a protected all-source rescan can clear a committed fallback marker."""
    raw = _file()
    raw["metadata"] = {"control": "\x00"}
    _dataset(db)
    if source == "dataset":
        with db.session() as session:
            dataset = session.get(DatasetRow, "fixture")
            assert dataset is not None
            dataset.files = [raw]
            session.commit()
            session.delete(dataset)
            session.commit()
    else:
        _version(db, "unsafe", 10, [raw])
        with db.engine.begin() as connection:
            connection.execute(text("DELETE FROM versions WHERE id = 'unsafe'"))
    assert _needs_python(db)
    with db.engine.begin() as connection:
        rebuild_file_discovery(connection, sqlite=db.sqlite)
    assert not _needs_python(db)


@pytest.mark.parametrize("source", ["dataset", "version"])
def test_v1_upgrade_scans_both_legacy_json_sources_and_installs_marker_hooks(
    db: Database, source: str
) -> None:
    """An old completed discovery generation must not skip the new compatibility scan."""
    _dataset(db)
    with db.engine.begin() as connection:
        for table in ("datasets", "versions"):
            name = f"datakeel_file_python_{table}"
            if db.sqlite:
                for operation in ("insert", "update"):
                    connection.execute(text(f"DROP TRIGGER {name}_{operation}"))
            else:
                connection.execute(text(f"DROP TRIGGER {name} ON {table}"))
        connection.execute(text("DELETE FROM file_discovery_checkpoints"))
        connection.execute(
            FileDiscoveryCheckpointRow.__table__.insert().values(generation="public-files-v1")
        )
    raw = _file()
    raw["metadata"] = {"control": "\x00"}
    if source == "dataset":
        with db.session() as session:
            dataset = session.get(DatasetRow, "fixture")
            assert dataset is not None
            dataset.files = [raw]
            session.commit()
    else:
        _version(db, "legacy", 10, [raw])
    assert not _needs_python(db)
    db.migrate()
    assert _needs_python(db)
    with db.engine.begin() as connection:
        connection.execute(text("UPDATE datasets SET files = '[]'"))
        connection.execute(text("DELETE FROM versions"))
    with db.engine.begin() as connection:
        rebuild_file_discovery(connection, sqlite=db.sqlite)
    assert not _needs_python(db)
    _version(db, "after-upgrade", 20, [raw])
    assert _needs_python(db)
