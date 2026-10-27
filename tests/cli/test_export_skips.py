# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""CLI exports keep working beside protected assets and name what they skipped."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from datakeel.core.models import AssetRef
from datakeel.storage.dataset_service import import_paths
from tests.assets.entry_helpers import publish

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

    from datakeel.storage.database import Database
    from tests.cli.conftest import Invoke


def _datasets(db: Database, tmp_path: Path) -> tuple[str, str, str]:
    protected_file = tmp_path / "protected.txt"
    protected_file.write_text("Generated protected export sample", encoding="utf-8")
    protected = import_paths(db, "protected-export", [protected_file])
    public_file = tmp_path / "public.txt"
    public_file.write_text("Generated public export sample", encoding="utf-8")
    public = import_paths(db, "public-export", [public_file])
    asset = publish(db, AssetRef(asset_id=protected.id), "restricted")
    return protected.id, public.id, asset.id


def test_openlineage_export_skips_protected_events_and_reports_ids_on_stderr(
    db: Database, tmp_path: Path, invoke: Invoke, capsys: pytest.CaptureFixture[str]
) -> None:
    """The README full export succeeds; the RunEvent array omits protected events."""
    protected, public, asset = _datasets(db, tmp_path)
    invoke("export", "--format", "openlineage")
    captured = capsys.readouterr()
    events = json.loads(captured.out)
    assert events
    assert public in captured.out
    assert protected not in captured.out
    assert "Skipped" in captured.err
    assert asset in captured.err
    assert "apply for access" in captured.err


def test_croissant_export_without_dataset_selects_first_readable_dataset(
    db: Database, tmp_path: Path, invoke: Invoke, capsys: pytest.CaptureFixture[str]
) -> None:
    """A protected first dataset is skipped by ID instead of failing the default export."""
    protected, _, _ = _datasets(db, tmp_path)
    invoke("export", "--format", "croissant")
    captured = capsys.readouterr()
    assert json.loads(captured.out)["name"] == "public-export"
    assert protected in captured.err
