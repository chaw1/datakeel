# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Generated source assets expose deterministic empty and healthy text evidence."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from datakeel.storage.dataset_service import import_paths

if TYPE_CHECKING:
    from pathlib import Path

    from datakeel.storage.database import Database
    from datakeel.storage.views import DatasetView


@pytest.fixture
def dataset(db: Database, tmp_path: Path) -> DatasetView:
    """Import two local text assets without contacting any external service."""
    paths = [tmp_path / "empty.txt", tmp_path / "healthy.txt"]
    paths[0].write_text("", encoding="utf-8")
    paths[1].write_text(
        "A complete generated sample containing useful quality evidence.", encoding="utf-8"
    )
    return import_paths(db, "agent-fixture", paths)
