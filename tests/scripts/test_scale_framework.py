# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Capacity tools retain reproducibility and failure evidence without touching shared state."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import select

from datakeel.storage.database import DatasetRow
from scripts.scale_bench import __main__ as cli
from scripts.scale_bench import common
from scripts.scale_bench.datasets import seed_dataset
from scripts.scale_bench.isolation import isolated
from scripts.scale_bench.models import SCALES, Config, Context
from scripts.scale_bench.versions import measure_selection_rejection

if TYPE_CHECKING:
    from pathlib import Path
    from typing import Literal

    from datakeel.storage.database import Database


def test_seed_when_repeated_has_identical_logical_files() -> None:
    """Same seed produces actual identical metadata, independent of private schema names."""
    manifests: list[object] = []
    for _ in range(2):
        with isolated(Config(scenario="B1")) as context:
            seed_dataset(context, 8)
            with context.db.session() as session:
                manifests.append(session.scalar(select(DatasetRow.files)))
    assert manifests[0] == manifests[1]


def test_cli_when_disk_low_writes_failed_json_before_opening_database(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Resource refusal remains a reviewable run instead of silently omitting its envelope."""
    output = tmp_path / "failed.json"
    monkeypatch.setattr("sys.argv", ["scale", "B1", "--output", str(output)])

    def low_space(_root: Path) -> int:
        message = "Insufficient fixture disk"
        raise OSError(message)

    monkeypatch.setattr(cli, "check_space", low_space)
    with pytest.raises(OSError, match="Insufficient"):
        cli.main()
    result = json.loads(output.read_text())
    assert result["status"] == "failed"
    assert result["error_type"] == "OSError"
    assert "database_version" not in result
    assert "source_sha256" in result


def test_resources_when_owned_fixture_exceeds_budget_refuses(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The cap includes real allocated file blocks, independent of payload logical size."""
    (tmp_path / "owned.txt").write_bytes(b"generated")
    context = Context(config=Config(scenario="B1"), scale=SCALES["S"], db=db, root=tmp_path)
    monkeypatch.setattr(common, "MAX_FIXTURE_BYTES", 0)
    with pytest.raises(OSError, match="8 GiB"):
        common.check_resources(context)


@pytest.mark.parametrize("size", ["M", "L"])
def test_version_when_full_selection_exceeds_public_limit_records_rejection(
    db: Database, tmp_path: Path, size: Literal["M", "L"]
) -> None:
    """Real schema rejection is measured before dataset access on both oversized scales."""
    config = Config(scenario="B1", size=size)
    context = Context(config=config, scale=SCALES[config.size], db=db, root=tmp_path)
    assert measure_selection_rejection(context, "unread-dataset") >= 0
