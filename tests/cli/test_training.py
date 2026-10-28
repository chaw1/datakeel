# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""The command-line training report exposes real findings without mutating source state."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from datakeel.cli import parser
from datakeel.cli.training import dispatch
from datakeel.storage.dataset_service import list_versions
from tests.storage.training_helpers import seed_training

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

    from datakeel.storage.database import Database


def test_training_cli_prints_measured_json_and_preserves_versions(
    db: Database, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """CLI and Agent consume the same pinned findings and never trigger cleaning."""
    dataset, _, run = seed_training(db, tmp_path)
    args = parser().parse_args(["training-quality", dataset, "--version-id", run.version_id])
    dispatch(db, args)
    result = json.loads(capsys.readouterr().out)
    assert result["records"] == 4
    assert result["issue_counts"]["exact_duplicate"] == 1
    assert len(list_versions(db, dataset)) == 1
