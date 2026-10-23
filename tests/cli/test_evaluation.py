# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Evaluation command runs the genuine offline suite and persists comparable runs."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

    from tests.cli.conftest import Invoke


def test_eval_when_repeated_reports_full_score_and_previous_comparison(
    invoke: Invoke,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Run all packaged golden conversations twice through the public command grammar."""
    invoke("eval")
    first = capsys.readouterr().out
    assert "32/32" in first
    assert "Previous: none" in first
    invoke("eval", "--json")
    report = json.loads(capsys.readouterr().out)
    assert report["passed"] == report["total"] == 32
    assert report["previous_id"]
    assert report["passed_delta"] == 0


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
