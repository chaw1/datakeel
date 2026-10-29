# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""SQL discovery shortlists retain Unicode rank, version identity and literal queries."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Event
from typing import TYPE_CHECKING

import pytest

from datakeel.core.file_queries import FileQuery
from datakeel.core.models import FileItem
from datakeel.core.search_models import SearchQuery
from datakeel.storage import search_sources
from datakeel.storage.database import DatasetRow, VersionRow
from datakeel.storage.dataset_service import list_files
from datakeel.storage.file_state import FileStateRow
from datakeel.storage.search import search_objects

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from datakeel.storage.database import Database


def _seed(db: Database) -> None:
    files = [
        FileItem(id=f"id-{index:03d}", filename=f"Alpha-{index:03d}.txt", path="")
        for index in range(60)
    ]
    files.extend(
        FileItem(id=identity, filename=name, path="")
        for identity, name in (
            ("alpha", "unrelated.txt"),
            ("alpha-prefix", "second.txt"),
            ("unicode", "Straße.txt"),
            ("accent", "École.txt"),
            ("literal", "100%_!.txt"),
        )
    )
    raw = [item.model_dump(mode="json") for item in files]
    with db.session() as session:
        session.add(DatasetRow(id="dataset", name="Generated", files=raw))
        session.flush()
        session.add(VersionRow(id="v0", dataset_id="dataset", manifest=raw, created_at=1))
        changed = [{**item, "filename": "changed-only.txt"} for item in raw]
        session.add(VersionRow(id="v1", dataset_id="dataset", manifest=changed, created_at=2))
        session.commit()


def test_discovery_when_shortlisted_preserves_exact_id_and_prefix_rank(db: Database) -> None:
    """A page limit applies after ranking across identities and names."""
    _seed(db)
    assert [item.id for item in search_objects(db, SearchQuery(q="ALPHA", limit=3))] == [
        "alpha",
        "alpha-prefix",
        "id-000",
    ]
    assert search_objects(db, SearchQuery(q="changed-only")) == []
    assert all(item.version_id == "v0" for item in search_objects(db, SearchQuery(q="Alpha-0")))


@pytest.mark.parametrize(
    ("query", "expected"), [("STRASSE", "unicode"), ("éCOLE", "accent"), ("%_!", "literal")]
)
def test_discovery_when_unicode_or_wildcard_keeps_literal_normalized_matches(
    db: Database, query: str, expected: str
) -> None:
    """Unicode candidates cannot disappear behind an ASCII SQL shortlist."""
    _seed(db)
    assert [item.id for item in search_objects(db, SearchQuery(q=query, limit=1))] == [expected]
    assert [item.id for item in list_files(db, "dataset", query=FileQuery(q=query, limit=1))] == [
        expected
    ]


def test_discovery_when_query_cannot_bind_as_database_text_keeps_literal_matching(
    db: Database,
) -> None:
    """A legal query string remains a Python substring filter on both databases."""
    _seed(db)
    query = "\0"
    assert search_objects(db, SearchQuery(q=query)) == []
    assert list_files(db, "dataset", query=FileQuery(q=query, limit=2)) == []
    assert list_files(db, "dataset", query=FileQuery(modality=query, limit=2)) == []


def _version(
    db: Database, identity: str, dataset: str, created: float, files: list[FileItem]
) -> None:
    raw = [item.model_dump(mode="json") for item in files]
    with db.session() as session:
        if session.get(DatasetRow, dataset) is None:
            session.add(DatasetRow(id=dataset, name=dataset, files=raw))
            session.flush()
        session.add(VersionRow(id=identity, dataset_id=dataset, created_at=created, manifest=raw))
        session.commit()


@pytest.mark.parametrize(
    ("identity", "name"), [("safe-id\0", "safe.txt"), ("safe-id", "safe\0.txt")]
)
def test_escaped_nul_file_identity_and_name_remain_searchable(
    db: Database, identity: str, name: str
) -> None:
    """Legal escaped JSON values remain visible to ordinary and NUL substring queries."""
    _version(db, "v0", "dataset", 1, [FileItem(id=identity, filename=name, path="")])
    for query in ("safe", "\0"):
        values = search_objects(db, SearchQuery(q=query))
        assert [(item.id, item.name, item.version_id) for item in values] == [
            (identity, name, "v0")
        ]


def test_escaped_nul_in_private_metadata_keeps_public_filename_visible(db: Database) -> None:
    """Opaque metadata never hides the public row or becomes a searchable field."""
    file = FileItem(id="safe-id", filename="safe.txt", path="", metadata={"note": "a\0b"})
    _version(db, "v0", "dataset", 1, [file])
    assert [item.id for item in search_objects(db, SearchQuery(q="safe"))] == [file.id]
    assert search_objects(db, SearchQuery(q="\0")) == []


@pytest.mark.parametrize("unsafe_earlier", [True, False])
def test_unsafe_manifest_fallback_keeps_first_identity_and_dataset_scoped_live_status(
    db: Database, *, unsafe_earlier: bool
) -> None:
    """An unsafe later or earlier row cannot alter first-version deduplication or status."""
    _version(
        db,
        "ä",
        "other",
        1,
        [FileItem(id="shared", filename="later.txt", path="")],
    )
    _version(
        db,
        "Z",
        "dataset",
        1,
        [FileItem(id="shared", filename="first.txt", path="")]
        + ([FileItem(id="unsafe\0", filename="École.txt", path="")] if unsafe_earlier else []),
    )
    _version(
        db,
        "zz",
        "dataset",
        2,
        [FileItem(id="shared", filename="changed.txt", path="")]
        + ([] if unsafe_earlier else [FileItem(id="unsafe\0", filename="École.txt", path="")]),
    )
    with db.session() as session:
        session.add_all(
            [
                FileStateRow(dataset_id="other", file_id="shared", deleted=True, revision=1),
                FileStateRow(dataset_id="dataset", file_id="shared", quarantined=True, revision=1),
            ]
        )
        session.commit()
    assert search_objects(db, SearchQuery(q="later")) == []
    assert search_objects(db, SearchQuery(q="changed")) == []
    first = search_objects(db, SearchQuery(q="first"))
    assert [(item.version_id, item.dataset_id, item.status) for item in first] == [
        ("Z", "dataset", "quarantined")
    ]
    assert [item.id for item in search_objects(db, SearchQuery(q="éCOLE"))] == ["unsafe\0"]
    with db.session() as session:
        state = session.get(FileStateRow, ("dataset", "shared"))
        assert state is not None
        state.deleted = True
        session.commit()
    assert search_objects(db, SearchQuery(q="first"))[0].status == "deleted"


def test_search_marker_and_candidates_share_one_snapshot(
    db: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A concurrent escaped version cannot make a mixed snapshot omit both valid matches."""
    _version(db, "old", "dataset", 1, [FileItem(id="shared", filename="needle old.txt", path="")])
    checked, release, committed = Event(), Event(), Event()
    original = search_sources.requires_python_files

    def paused(session: Session) -> bool:
        result = original(session)
        assert not result
        checked.set()
        assert release.wait(10)
        return result

    def write_unsafe_version() -> None:
        _version(
            db,
            "earlier",
            "dataset",
            0,
            [
                FileItem(id="shared", filename="different.txt", path=""),
                FileItem(id="unsafe\0", filename="needle new.txt", path=""),
            ],
        )
        committed.set()

    monkeypatch.setattr(search_sources, "requires_python_files", paused)
    with ThreadPoolExecutor(max_workers=2) as pool:
        reader = pool.submit(search_objects, db, SearchQuery(q="needle"))
        try:
            assert checked.wait(10)
            writer = pool.submit(write_unsafe_version)
            committed_before_release = committed.wait(5)
        finally:
            release.set()
        values = reader.result(timeout=10)
        writer.result(timeout=10)
    assert committed_before_release
    assert [(item.id, item.version_id) for item in values] == [("shared", "old")]
