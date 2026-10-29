# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Bounded file pages preserve overlays, ownership, literal filtering and legacy reads."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sqlalchemy import event, inspect
from sqlalchemy.orm import Session

from datakeel.api.app import create_app
from datakeel.core.errors import NotFoundError
from datakeel.core.file_queries import FileQuery
from datakeel.core.models import FileItem
from datakeel.storage.database import DatasetRow, VersionRow
from datakeel.storage.dataset_service import get_dataset, list_datasets, list_files
from datakeel.storage.file_pages import read_file_page
from datakeel.storage.file_state import FileStateRow, overlay_files
from tests.asgi_client import TestClient

if TYPE_CHECKING:
    from sqlalchemy.engine import Connection

    from datakeel.storage.database import Database


def _seed(db: Database, count: int = 64) -> list[FileItem]:
    items = [
        FileItem(
            id=f"file-{index}",
            path="private/location",
            filename=f"file-{index}.txt",
            modality="text",
            metadata={"index": index},
        )
        for index in range(count)
    ]
    with db.session() as session:
        raw = [item.model_dump(mode="json") for item in items]
        session.add(DatasetRow(id="dataset", name="Generated", files=raw))
        session.flush()
        session.add(VersionRow(id="version", dataset_id="dataset", manifest=raw))
        session.add(FileStateRow(dataset_id="dataset", file_id="file-0", deleted=True))
        session.add(
            FileStateRow(dataset_id="dataset", file_id="file-2", quarantined=True, revision=2)
        )
        session.commit()
    return items


@pytest.mark.parametrize("count", [16, 64])
def test_overlay_when_input_grows_uses_one_query_and_preserves_state(
    db: Database, count: int
) -> None:
    """Sparse overlays no longer issue a SELECT for every immutable file."""
    items = _seed(db, count)
    statements: list[str] = []
    with db.session() as session:

        def observed(*args: object) -> None:
            statements.append(str(args[2]))

        event.listen(db.engine, "before_cursor_execute", observed)
        try:
            result = overlay_files(session, "dataset", items)
        finally:
            event.remove(db.engine, "before_cursor_execute", observed)
    assert len(statements) == 1
    assert len(result) == count - 1
    assert result[1].metadata["quarantined"] is True
    assert result[1].metadata["state_revision"] == 2


def test_pages_when_deleted_and_quarantined_apply_state_before_pagination(db: Database) -> None:
    """Pages are filled after deletion and retain immutable ordinal order and overlay metadata."""
    _seed(db)
    assert [item.id for item in list_files(db, "dataset", query=FileQuery(limit=2))] == [
        "file-1",
        "file-2",
    ]
    assert list_files(db, "dataset", query=FileQuery(limit=2))[1].metadata["quarantined"] is True
    assert [
        item.id for item in list_files(db, "dataset", "version", query=FileQuery(limit=2, offset=2))
    ] == ["file-3", "file-4"]
    assert get_dataset(db, "dataset").file_count == 63
    assert len(list_files(db, "dataset")) == 63
    assert len(list_files(db, "dataset", query=FileQuery())) == 63


@pytest.mark.parametrize("control", ["\0", "\ud800"], ids=["nul", "surrogate"])
def test_dataset_summaries_when_metadata_needs_python_keep_exact_deleted_count(
    db: Database, control: str
) -> None:
    """Opaque JSON strings cannot break either dataset summary's live deletion count."""
    items = [
        FileItem(
            id=f"file-{index}",
            path="",
            filename=f"ordinary-{index}.txt",
            metadata={"note": f"nested{control}value"},
        ).model_dump(mode="json")
        for index in range(3)
    ]
    with db.session() as session:
        session.add(DatasetRow(id="dataset", name="Generated", files=items))
        session.flush()
        session.add(FileStateRow(dataset_id="dataset", file_id="file-0", deleted=True))
        session.commit()
    assert get_dataset(db, "dataset").file_count == 2
    assert [(item.id, item.file_count) for item in list_datasets(db)] == [("dataset", 2)]


def test_dataset_summaries_when_json_is_safe_leave_large_manifest_deferred(db: Database) -> None:
    """Normal deletion summaries use SQL counts without loading the complete original JSON."""
    _seed(db)
    loaded: list[DatasetRow] = []

    def observed(_session: Session, row: object) -> None:
        if isinstance(row, DatasetRow):
            loaded.append(row)

    event.listen(Session, "loaded_as_persistent", observed)
    try:
        assert get_dataset(db, "dataset").file_count == 63
        assert list_datasets(db)[0].file_count == 63
    finally:
        event.remove(Session, "loaded_as_persistent", observed)
    assert len(loaded) == 2
    assert all("files" in inspect(row).unloaded for row in loaded)


def test_dataset_summary_when_first_unsafe_write_commits_mid_count_keeps_one_snapshot(
    db: Database,
) -> None:
    """A new unsafe manifest cannot race past the marker check into SQL JSON extraction."""
    items = _seed(db, 3)
    published = False

    def publish(_connection: Connection, _cursor: object, statement: str, *_args: object) -> None:
        nonlocal published
        if published or not statement.startswith("SELECT json_array_length(datasets.files)"):
            return
        published = True
        with db.session() as writer:
            row = writer.get(DatasetRow, "dataset")
            assert row is not None
            row.files = [
                item.model_copy(update={"metadata": {"note": "nested\0value"}}).model_dump(
                    mode="json"
                )
                for item in items[:2]
            ]
            writer.commit()

    event.listen(db.engine, "before_cursor_execute", publish)
    try:
        assert get_dataset(db, "dataset").file_count == 2
    finally:
        event.remove(db.engine, "before_cursor_execute", publish)
    assert published
    assert get_dataset(db, "dataset").file_count == 1


def test_overlay_when_page_is_small_loads_only_matching_state_rows(db: Database) -> None:
    """A small response stays bounded even when the dataset accumulates unrelated overlays."""
    items = _seed(db)
    loaded: list[str] = []

    def observed(_session: Session, row: object) -> None:
        if isinstance(row, FileStateRow):
            loaded.append(row.file_id)

    event.listen(Session, "loaded_as_persistent", observed)
    try:
        with db.session() as session:
            assert [item.id for item in overlay_files(session, "dataset", [items[2]])] == ["file-2"]
    finally:
        event.remove(Session, "loaded_as_persistent", observed)
    assert loaded == ["file-2"]


def test_pages_when_filtered_have_literal_substrings_and_modality(db: Database) -> None:
    """Filters compose before slicing and SQL wildcard characters remain literal."""
    _seed(db)
    result = list_files(db, "dataset", query=FileQuery(q="FILE-1", modality="text", limit=4))
    assert [item.id for item in result] == ["file-1", "file-10", "file-11", "file-12"]
    assert list_files(db, "dataset", query=FileQuery(q="%", limit=4)) == []
    assert list_files(db, "dataset", query=FileQuery(modality="image", limit=4)) == []


def test_pages_when_version_belongs_elsewhere_or_dataset_missing_reject(db: Database) -> None:
    """Direct SQL expansion keeps exact version ownership validation."""
    _seed(db)
    with db.session() as session:
        session.add(DatasetRow(id="other", name="Other", files=[]))
        session.commit()
    with pytest.raises(NotFoundError, match="Version not found"):
        list_files(db, "other", "version", query=FileQuery(limit=1))
    with pytest.raises(NotFoundError, match="Dataset not found"):
        list_files(db, "missing", query=FileQuery(limit=1))


def test_http_pages_when_bounded_preserve_response_shape_and_validation(db: Database) -> None:
    """Optional parameters extend the existing route and never expose physical file paths."""
    _seed(db)
    with TestClient(create_app(db)) as client:
        result = client.get("/api/datasets/dataset/files?limit=2&offset=1")
        assert result.status_code == 200
        assert [item["id"] for item in result.json()] == ["file-2", "file-3"]
        assert "private/location" not in result.text
        for invalid in ("limit=0", "limit=1001", "offset=-1"):
            assert client.get(f"/api/datasets/dataset/files?{invalid}").status_code == 422
        assert client.get("/api/datasets/dataset/files?q=%00&limit=2").json() == []


def test_pages_when_metadata_needs_python_filtering_slice_after_exact_matches(
    db: Database,
) -> None:
    """JSON strings outside SQL text retain exact filtering before offset and limit."""
    value = "\0"
    items = [FileItem(id="ordinary", path="", filename="ordinary.txt", modality="text")]
    items.extend(
        FileItem(id=f"control-{index}", path="", filename=f"control-{value}.txt", modality=value)
        for index in range(3)
    )
    with db.session() as session:
        raw = [item.model_dump(mode="json") for item in items]
        session.add(DatasetRow(id="dataset", name="Generated", files=raw))
        session.flush()
        session.add(VersionRow(id="version", dataset_id="dataset", manifest=raw))
        session.add(FileStateRow(dataset_id="dataset", file_id="control-0", deleted=True))
        session.commit()
    for query in (
        FileQuery(q=value, offset=1, limit=1),
        FileQuery(modality=value, offset=1, limit=1),
    ):
        for version in (None, "version"):
            assert [item.id for item in list_files(db, "dataset", version, query=query)] == [
                "control-2"
            ]


@pytest.mark.parametrize("field", ["metadata", "filename", "modality", "id"])
def test_pages_when_stored_json_has_nul_keeps_ordinary_queries_and_live_state(
    db: Database, field: str
) -> None:
    """A safe query must still read valid original JSON that SQL cannot expand."""
    items = [
        FileItem(id=f"file-{index}", path="", filename=f"ordinary-{index}.txt")
        for index in range(3)
    ]
    if field == "metadata":
        items = [item.model_copy(update={"metadata": {"note": "nested\0value"}}) for item in items]
    else:
        items = [
            item.model_copy(update={field: getattr(item, field) + "\0value"}) for item in items
        ]
    with db.session() as session:
        raw = [item.model_dump(mode="json") for item in items]
        session.add(DatasetRow(id="dataset", name="Generated", files=raw))
        session.flush()
        session.add(VersionRow(id="version", dataset_id="dataset", manifest=raw))
        if field != "id":
            session.add(FileStateRow(dataset_id="dataset", file_id=items[0].id, deleted=True))
        session.commit()
    expected = items[1 if field == "id" else 2].id
    for version in (None, "version"):
        for query in (FileQuery(offset=1, limit=1), FileQuery(q="ordinary", offset=1, limit=1)):
            assert [item.id for item in list_files(db, "dataset", version, query=query)] == [
                expected
            ]


def test_page_when_first_unsafe_write_commits_mid_read_keeps_one_snapshot(db: Database) -> None:
    """The marker and JSON expansion cannot observe opposite sides of a concurrent commit."""
    original = FileItem(id="file", path="", filename="alpha.txt")
    with db.session() as session:
        session.add(
            DatasetRow(id="dataset", name="Generated", files=[original.model_dump(mode="json")])
        )
        session.commit()
    published = False

    def publish(_connection: Connection, _cursor: object, statement: str, *_args: object) -> None:
        nonlocal published
        if published or not statement.startswith("SELECT j.value FROM datasets"):
            return
        published = True
        with db.session() as writer:
            row = writer.get(DatasetRow, "dataset")
            assert row is not None
            row.files = [
                original.model_copy(
                    update={"filename": "changed.txt", "metadata": {"note": "nested\0value"}}
                ).model_dump(mode="json")
            ]
            writer.commit()

    event.listen(db.engine, "before_cursor_execute", publish)
    try:
        assert [
            item.filename for item in list_files(db, "dataset", query=FileQuery(q="alpha"))
        ] == ["alpha.txt"]
    finally:
        event.remove(db.engine, "before_cursor_execute", publish)
    assert published
    assert [item.filename for item in list_files(db, "dataset", query=FileQuery(q="changed"))] == [
        "changed.txt"
    ]


def test_page_when_caller_has_pending_writes_does_not_change_or_rollback_transaction(
    db: Database,
) -> None:
    """An existing write transaction uses Python reads and remains owned by its caller."""
    with db.session() as session:
        session.add(
            DatasetRow(
                id="pending",
                name="Generated",
                files=[FileItem(id="file", path="", filename="alpha.txt").model_dump(mode="json")],
            )
        )
        session.flush()
        assert [
            item.filename for item in read_file_page(session, "pending", None, FileQuery())
        ] == ["alpha.txt"]
        session.rollback()
    with pytest.raises(NotFoundError):
        list_files(db, "pending", query=FileQuery())
