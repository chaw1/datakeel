# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Generated datasets with deliberately different per-file quality evidence."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    from datakeel.storage.database import Database
    from datakeel.storage.views import DatasetView

import pytest

from datakeel.storage.dataset_service import import_paths


@pytest.fixture
def dataset(db: Database, tmp_path: Path) -> DatasetView:
    """Provide the dataset test fixture."""
    paths = [tmp_path / name for name in ("good.txt", "empty.txt", "short.txt")]
    for path, content in zip(
        paths, ("A complete generated observation with sufficient detail.", "", "abc"), strict=True
    ):
        path.write_text(content, encoding="utf-8")
    return import_paths(db, "generated-objects", paths, {"label": "fixture"})
