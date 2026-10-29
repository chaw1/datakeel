# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Command-line distribution and leakage use the same persisted version measurements."""

from pathlib import Path

import pytest
from pydantic import TypeAdapter

from datakeel.cli import parser
from datakeel.cli.training import dispatch
from datakeel.core.errors import ValidationError
from datakeel.core.training_models import LeakageReport, SplitComparison, SplitSet
from datakeel.harness.training_cases import seed_training_case
from datakeel.storage.database import Database
from datakeel.storage.training_store import list_splits


def test_cli_training_reads_previews_saves_and_compares(
    db: Database, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """An explicit create persists a split; the two question commands only read its facts."""
    fixture = seed_training_case(db, tmp_path)

    def command(*arguments: str) -> str:
        dispatch(db, parser().parse_args(["training", *arguments]))
        return capsys.readouterr().out

    preview = SplitSet.model_validate_json(command("distribution", fixture.dataset_id, "--json"))
    assert [item.count for item in preview.distributions] == [80, 10, 10]
    assert not list_splits(db, fixture.dataset_id, fixture.version_id)
    leakage = LeakageReport.model_validate_json(command("leakage", fixture.dataset_id))
    assert sorted(item.kind for item in leakage.pairs) == ["exact", "image"]
    saved = SplitSet.model_validate_json(
        command(
            "create",
            fixture.dataset_id,
            "--name",
            "cli",
            "--test",
            "0",
            "--val",
            "0.2",
            "--text-threshold",
            "0",
        )
    )
    assert [item.count for item in saved.distributions] == [80, 20, 0]
    assert saved.request.text_threshold == 0
    assert len(TypeAdapter(list[SplitSet]).validate_json(command("list", fixture.dataset_id))) == 1
    detail = SplitSet.model_validate_json(
        command("distribution", fixture.dataset_id, "--split-set", saved.id)
    )
    assert detail == saved
    checked = LeakageReport.model_validate_json(
        command("leakage", fixture.dataset_id, "--split-set", saved.id)
    )
    assert checked.pairs == ()
    compared = SplitComparison.model_validate_json(
        command("compare", fixture.dataset_id, saved.id, saved.id)
    )
    assert compared.changed_sample_ids == ()
    with pytest.raises(ValidationError, match="requested version"):
        command("compare", fixture.dataset_id, saved.id, saved.id, "--version", "other-version")
