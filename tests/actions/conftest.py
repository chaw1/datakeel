# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Generated local datasets for controlled mutation tests."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from datakeel.core.models import FileItem
from datakeel.storage.dataset_service import import_paths, list_files
from datakeel.storage.views import DatasetView

if TYPE_CHECKING:
    from pathlib import Path

    from datakeel.storage.database import Database

type DatasetFixture = tuple[DatasetView, list[FileItem]]


@pytest.fixture
def dataset(db: Database, tmp_path: Path) -> DatasetFixture:
    """Provide the dataset test fixture."""
    paths = [tmp_path / f"action-{index}.txt" for index in range(3)]
    for index, path in enumerate(paths):
        path.write_text("Generated action fixture. " * index)
    created = import_paths(db, "action-fixture", paths)
    return created, list_files(db, created.id)
