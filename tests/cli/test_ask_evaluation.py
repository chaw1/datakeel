# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Public question-evaluation grammar persists truthful reports without threshold exit failures."""

from __future__ import annotations

from typing import TYPE_CHECKING

from datakeel.core.ask_eval import AskEvalReport
from datakeel.storage.ask_evaluations import list_ask_evaluations

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

    from datakeel.storage.database import Database
    from tests.cli.conftest import Invoke


def test_eval_ask_custom_suite_reports_threshold_miss_without_failed_exit(
    invoke: Invoke, db: Database, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """CLI options dispatch to the real isolated pipeline and retain provider=ask records."""
    path = tmp_path / "questions.yaml"
    path.write_text(
        "reference_instant: '2026-10-01T00:00:00Z'\nquestions:\n"
        "- id: unknown\n  question: 品牌知名度提高了多少\n  expected_status: unanswerable\n"
    )
    invoke("eval-ask", "--questions", str(path), "--json")
    report = AskEvalReport.model_validate_json(capsys.readouterr().out)
    assert report.provider == "ask"
    assert report.refused == report.unanswerable == 1
    assert report.evidence_complete == 1
    assert not report.threshold_met
    assert list_ask_evaluations(db) == [report]
