# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Evaluation command runs the genuine offline suite and persists comparable runs."""

from __future__ import annotations

import json
import shutil
from typing import TYPE_CHECKING

import pytest

from datakeel.harness.resources import contract_path

if TYPE_CHECKING:
    from pathlib import Path

    from tests.cli.conftest import Invoke


def test_legacy_eval_when_repeated_reports_full_score_and_previous_comparison(
    invoke: Invoke,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Preserve the original 32-case CLI baseline and compare its repeated execution."""
    for path in contract_path("golden").glob("*.yaml"):
        if int(path.name.split("-", 1)[0]) <= 32:
            shutil.copyfile(path, tmp_path / path.name)
    invoke("eval", "--golden-dir", str(tmp_path))
    first = capsys.readouterr().out
    assert "32/32" in first
    assert "Previous: none" in first
    invoke("eval", "--golden-dir", str(tmp_path), "--json")
    report = json.loads(capsys.readouterr().out)
    assert report["passed"] == report["total"] == 32
    assert report["previous_id"]
    assert report["passed_delta"] == 0


def test_default_eval_includes_all_graph_conversations(
    invoke: Invoke, capsys: pytest.CaptureFixture[str]
) -> None:
    """The normal public command runs all original and graph contracts together."""
    invoke("eval", "--json")
    report = json.loads(capsys.readouterr().out)
    assert report["passed"] == report["total"] == 44
    assert len([case for case in report["cases"] if "-kg-" in case["id"]]) == 7


def test_eval_when_assertion_fails_reports_case_and_nonzero_exit(
    invoke: Invoke,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Make an unmet answer assertion fail the CLI instead of merely printing a score."""
    (tmp_path / "failure.yaml").write_text(
        "id: failing\ndescription: Synthetic expectation\nturns:\n"
        "- input: hello\n  script:\n  - content: actual\n"
        "expect:\n  answer_contains: [missing]\n",
        encoding="utf-8",
    )
    with pytest.raises(SystemExit, match="1"):
        invoke("eval", "--golden-dir", str(tmp_path))
    assert "FAIL failing:" in capsys.readouterr().out
