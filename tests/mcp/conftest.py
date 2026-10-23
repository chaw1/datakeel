# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Generated data shared by real protocol and controlled MCP tool tests."""

from pathlib import Path

import pytest

from datakeel.storage.database import Database
from datakeel.storage.dataset_service import import_paths
from datakeel.storage.views import DatasetView


@pytest.fixture
def dataset(db: Database, tmp_path: Path) -> DatasetView:
    """Import one empty and one usable local text file for selection and approval."""
    paths = [tmp_path / "empty.txt", tmp_path / "healthy.txt"]
    for index, path in enumerate(paths):
        path.write_text("Generated protocol fixture. " * index)
    return import_paths(db, "mcp-fixture", paths)
