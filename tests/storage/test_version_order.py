# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Version comparison aligns file identities in code-point order on every database collation."""

from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import DBAPIError

from datakeel.core.errors import ConflictError, ExecutionError
from datakeel.core.models import FileItem
from datakeel.storage.database import Database, VersionRow
from datakeel.storage.dataset_service import import_paths
from datakeel.storage.version_diff import compare_versions
from datakeel.storage.version_stream import ordered_identities

BEFORE = ("File-c", "file_a")
AFTER = ("file-b", "File-c")


def _mixed_case_versions(db: Database, tmp_path: Path) -> tuple[str, str, str]:
    path = tmp_path / "ordered.txt"
    path.write_text("Generated ordering sample.", encoding="utf-8")
    dataset = import_paths(db, "ordering-example", [path])
    with db.session() as session:
        original = session.scalar(select(VersionRow).where(VersionRow.dataset_id == dataset.id))
        assert original is not None
        template = FileItem.model_validate(original.manifest[0])
        original.manifest = [
            template.model_copy(update={"id": item}).model_dump(mode="json") for item in BEFORE
        ]
        other = VersionRow(
            dataset_id=dataset.id,
            manifest=[
                template.model_copy(update={"id": item}).model_dump(mode="json") for item in AFTER
            ],
        )
        session.add(other)
        session.commit()
        return dataset.id, original.id, other.id


def _assert_aligned(db: Database, tmp_path: Path) -> None:
    dataset, before, after = _mixed_case_versions(db, tmp_path)
    result = compare_versions(db, dataset, before, after)
    assert result.counts.model_dump() == {
        "added": 1,
        "removed": 1,
        "content_changed": 0,
        "metadata_changed": 0,
        "unchanged": 1,
    }
    categories = {entry.file_id: entry.category for entry in result.files}
    assert categories == {"file_a": "removed", "file-b": "added", "File-c": "unchanged"}


def test_mixed_case_and_hyphen_identities_align(db: Database, tmp_path: Path) -> None:
    """Upper case, hyphens and underscores sort by code point, matching the Python merge."""
    _assert_aligned(db, tmp_path)


def test_stream_order_violation_is_reported_instead_of_misclassified() -> None:
    """A database ordering that disagrees with code-point order stops the comparison."""
    items = [FileItem.model_validate(_item(identity)) for identity in ("file_a", "File-c")]
    with pytest.raises(ExecutionError, match="code-point order"):
        list(ordered_identities(iter(items)))
    duplicate = [FileItem.model_validate(_item("same")) for _ in range(2)]
    with pytest.raises(ConflictError, match="duplicate"):
        list(ordered_identities(iter(duplicate)))
    ordered = [FileItem.model_validate(_item(identity)) for identity in ("File-c", "file-b")]
    assert [item.id for item in ordered_identities(iter(ordered))] == ["File-c", "file-b"]


@pytest.fixture
def icu_db(db: Database) -> Iterator[Database]:
    """Create a scratch PostgreSQL database whose default collation is ICU en-US."""
    if db.sqlite:
        pytest.skip("ICU collations exist only on PostgreSQL")
    name = "datakeel_icu_" + uuid4().hex[:12]
    # A separate engine: the per-test schema hook on the fixture engine opens a transaction.
    admin = create_engine(db.engine.url, isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        try:
            connection.execute(
                text(
                    f"CREATE DATABASE \"{name}\" TEMPLATE template0 ENCODING 'UTF8' "
                    "LOCALE_PROVIDER icu ICU_LOCALE 'en-US' LOCALE 'C'"
                )
            )
        except DBAPIError as error:
            admin.dispose()
            pytest.skip(f"This PostgreSQL server cannot create an ICU database: {error.orig}")
    database = Database(db.engine.url.set(database=name).render_as_string(hide_password=False))
    try:
        database.migrate()
        yield database
    finally:
        database.engine.dispose()
        with admin.connect() as connection:
            connection.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))
        admin.dispose()


def test_icu_default_collation_still_aligns(icu_db: Database, tmp_path: Path) -> None:
    """ICU orders file_a before File-c; the stream must still follow code-point order."""
    with icu_db.engine.connect() as connection:
        icu_order = connection.execute(
            text("SELECT id FROM (VALUES ('File-c'), ('file-b'), ('file_a')) AS t(id) ORDER BY id")
        ).scalars()
        assert list(icu_order) == ["file_a", "file-b", "File-c"]
    _assert_aligned(icu_db, tmp_path)


def _item(identity: str) -> dict[str, object]:
    return {
        "id": identity,
        "path": f"generated/{identity}.txt",
        "filename": f"{identity}.txt",
        "sha256": "a" * 64,
        "size": 1,
        "modality": "text",
    }
