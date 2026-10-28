# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Training goldens inspect actual record measurements and reject fabricated tool counts."""

from __future__ import annotations

from typing import TYPE_CHECKING

from datakeel.harness.cases import load_cases
from datakeel.harness.execution import run_case
from datakeel.storage.training_reads import read_training_result

if TYPE_CHECKING:
    import pytest

    from datakeel.core.data_asset_models import AccessContext
    from datakeel.core.training_governance import TrainingQualityQuery, TrainingQualityResult
    from datakeel.storage.database import Database


def test_training_golden_measures_actual_invalid_and_duplicate_records() -> None:
    """A scripted conclusion must agree with the production read tool's observed counts."""
    case = next(item for item in load_cases() if item.id == "46-training-quality")
    report = run_case(case, "fake")
    assert report.passed, report.failures


def test_training_golden_rejects_mutated_issue_counts(monkeypatch: pytest.MonkeyPatch) -> None:
    """Changing the real response to claim no defects must make the content assertion fail."""

    def corrupted(
        db: Database, query: TrainingQualityQuery, *, access: AccessContext | None = None
    ) -> TrainingQualityResult:
        result = read_training_result(db, query, access=access)
        return result.model_copy(
            update={"report": result.report.model_copy(update={"issue_counts": {}})}
        )

    monkeypatch.setattr("datakeel.ontology.training_functions.read_training_result", corrupted)
    case = next(item for item in load_cases() if item.id == "46-training-quality")
    report = run_case(case, "fake")
    assert not report.passed
    assert any("Tool content mismatch: get_training_quality" in item for item in report.failures)
