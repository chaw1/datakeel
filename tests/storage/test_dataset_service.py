# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Storage service contracts preserve isolation and manifest identity."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    from datakeel.storage.database import Database

import pytest

from datakeel.core.errors import NotFoundError
from datakeel.storage.database import DatasetRow
from datakeel.storage.dataset_service import (
    import_paths,
    list_files,
    list_versions,
    resolve_download,
)
from datakeel.storage.views import DatasetView


def test_path_import_when_published_returns_model_without_database_row(
    db: Database, tmp_path: Path
) -> None:
    """Verify path import when published returns model without database row."""
    source = tmp_path / "sample.txt"
    source.write_text("Generated content", encoding="utf-8")
    result = import_paths(db, "sample", [source])
    assert isinstance(result, DatasetView)


def test_version_selection_when_from_another_dataset_is_rejected(
    db: Database, tmp_path: Path
) -> None:
    """Verify version selection when from another dataset is rejected."""
    source = tmp_path / "sample.txt"
    source.write_text("Generated content", encoding="utf-8")
    first = import_paths(db, "one", [source])
    second = import_paths(db, "two", [source])
    version = list_versions(db, first.id)[0]
    with pytest.raises(NotFoundError, match="Version not found"):
        list_files(db, second.id, version.id)


def test_version_selection_when_owned_returns_immutable_manifest(
    db: Database, tmp_path: Path
) -> None:
    """Verify version selection when owned returns immutable manifest."""
    source = tmp_path / "sample.txt"
    source.write_text("Generated content", encoding="utf-8")
    created = import_paths(db, "one", [source])
    version = list_versions(db, created.id)[0]
    assert list_files(db, created.id, version.id) == version.manifest


def test_download_when_object_key_missing_is_rejected(db: Database, tmp_path: Path) -> None:
    """Verify download when object key missing is rejected."""
    source = tmp_path / "sample.txt"
    source.write_text("Generated content", encoding="utf-8")
    created = import_paths(db, "one", [source])
    file = list_files(db, created.id)[0]
    with db.session() as session:
        row = session.get(DatasetRow, created.id)
        assert row is not None
        row.files = [{**item, "metadata": {}} for item in row.files]
        session.commit()
    with pytest.raises(NotFoundError, match="File object not found"):
        resolve_download(db, created.id, file.id)
