# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Field quality weights only measured rules and reports redacted evidence."""

import pytest

from datakeel.core.standard_history_models import StandardsReport
from datakeel.core.standard_models import (
    ColumnCheck,
    ColumnMapping,
    ColumnProfile,
    StandardViolation,
)
from datakeel.quality.standards import score_standards, standards_report
from datakeel.standards.coverage import summarize_coverage


def _report(checks: tuple[ColumnCheck, ...]) -> StandardsReport:
    profiles = tuple(
        ColumnProfile(column_id=item.column_id, name=item.column_id, data_type="string")
        for item in checks
    )
    mappings = tuple(
        ColumnMapping(column_id=item.column_id, standard_code=item.standard_code) for item in checks
    )
    return StandardsReport(
        profiles=profiles,
        mappings=mappings,
        checks=checks,
        coverage=summarize_coverage(profiles, mappings, checks),
    )


@pytest.mark.parametrize(
    ("passing", "grade"), [(0, "poor"), (6, "fair"), (8, "good"), (9, "excellent")]
)
def test_quality_uses_evaluated_rules_and_reweights_unmeasured_dimensions(
    passing: int, grade: str
) -> None:
    """Value-row counts never make an incompatible column type nearly compliant."""
    checks = tuple(
        ColumnCheck(
            column_id=str(index),
            standard_code="label",
            row_count=1000,
            checked_rules=("type",),
            violations=()
            if index < passing
            else (StandardViolation(rule="type", count=1000, message="Wrong declared type"),),
        )
        for index in range(10)
    )
    quality = score_standards(_report(checks))
    assert quality.total == passing * 10
    assert quality.grade == grade
    assert quality.dimensions["consistency"].failed_rules == 10 - passing
    assert quality.dimensions["completeness"].score is None
    assert quality.dimensions["distribution"].weight == 0


def test_unknown_rules_remain_unmeasured_and_report_warns_about_evidence() -> None:
    """Missing profiling never earns full credit or a passing grade."""
    source = _report(
        (
            ColumnCheck(
                column_id="note",
                standard_code="label",
                row_count=0,
                skipped_rules=("type: unavailable",),
            ),
        )
    )
    quality = score_standards(source)
    assert quality.total is None
    assert quality.grade == "unmeasured"
    assert quality.skipped_rules == 1
    assert quality.fully_checked_columns == 0
    report = standards_report(source)
    assert report.source == "baseline"
    assert report.llm_body is None
    assert "unmeasured" in report.body
    assert "skipped rules remain unverified" in report.body


def test_failures_enter_their_quality_dimensions_and_analysis_report() -> None:
    """Completeness, consistency and distribution use their own failed rule populations."""
    source = _report(
        (
            ColumnCheck(
                column_id="customer",
                standard_code="customer_name",
                row_count=3,
                checked_rules=("type", "length", "required", "pattern"),
                violations=(
                    StandardViolation(
                        rule="length", count=1, samples=("[REDACTED]",), message="Long"
                    ),
                    StandardViolation(rule="required", count=1, message="Missing"),
                    StandardViolation(rule="pattern", count=1, message="Shape"),
                ),
            ),
        )
    )
    quality = score_standards(source)
    assert quality.dimensions["completeness"].score == 0
    assert quality.dimensions["consistency"].score == 50
    assert quality.dimensions["distribution"].score == 0
    assert quality.total == 20
    assert {issue.dimension for issue in quality.issues} == {
        "completeness",
        "consistency",
        "distribution",
    }
    report = standards_report(source)
    assert "[REDACTED]" in report.body
    assert "length; count=1" in report.body
    assert "3 failed rules" in report.baseline_verification
