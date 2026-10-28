# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Connect actual table operators to measured quality and evidence-based reports."""

from __future__ import annotations

import hashlib
from pathlib import Path

from datakeel.core.models import FileItem
from datakeel.operators.table.profile import OPERATOR as PROFILE
from datakeel.operators.timeseries.anomaly import OPERATOR as ANOMALY
from datakeel.operators.timeseries.gaps import OPERATOR as GAPS
from datakeel.operators.timeseries.order_dedup import OPERATOR as ORDER
from datakeel.operators.timeseries.timestamp_normalize import OPERATOR as TIMESTAMP
from datakeel.operators.timeseries.unit_check import OPERATOR as UNITS
from datakeel.quality.report import build_report
from datakeel.quality.scoring import score_quality
from datakeel.quality.tabular import assess_tables


def _file(tmp_path: Path, content: str, filename: str = "readings.csv") -> FileItem:
    path = tmp_path / filename
    path.write_text(content, encoding="utf-8")
    return FileItem(
        path=str(path),
        filename=filename,
        size=len(content.encode()),
        sha256=hashlib.sha256(content.encode()).hexdigest(),
        modality="table",
    )


def test_profile_nulls_reduce_completeness_with_column_and_source_rows(tmp_path: Path) -> None:
    """An observed null reduces completeness by its share of measured table cells."""
    source = _file(tmp_path, "id,temperature\nA,21\nB,\n")
    profiled = PROFILE.run([source], tmp_path / "profile").files
    Path(source.path).unlink()
    quality = score_quality(profiled)
    assert quality.dimensions["completeness"].score == 75
    assert quality.tabular is not None
    finding = next(item for item in quality.tabular.files[0].findings if item.rule == "null_values")
    assert finding.column == "temperature"
    assert finding.rows == (3,)
    assert any(
        issue.code == "null_values" and "temperature" in issue.message for issue in quality.issues
    )


def test_gap_scoring_uses_missing_samples_and_preserves_duration(tmp_path: Path) -> None:
    """Observed gap endpoints are retained; only absent scheduled samples are missing."""
    source = _file(
        tmp_path,
        "timestamp,device_id,temperature\n1700000000000,A,20\n1700000003000,A,21\n",
    )
    files = GAPS.run([source], tmp_path / "gaps", {"expected_interval_ms": 1000}).files
    quality = score_quality(files)
    assert quality.dimensions["completeness"].score == 50
    assert quality.tabular is not None
    evidence = quality.tabular.files[0]
    assert evidence.total_gap_ms == 2000
    finding = next(item for item in evidence.findings if item.rule == "sampling_gap")
    assert (finding.column, finding.device, finding.rows) == ("timestamp", "A", (2, 3))
    assert (finding.start_ms, finding.end_ms) == (1700000000000, 1700000003000)
    assert "2 expected samples missing" in finding.detail


def test_order_and_duplicates_reduce_corresponding_dimensions(tmp_path: Path) -> None:
    """The quality view retains pre-repair evidence after sorting and deduplication."""
    source = _file(
        tmp_path,
        "timestamp,device_id,temperature\n"
        "1700000002000,A,22\n1700000000000,A,20\n1700000000000,A,20\n1700000001000,A,21\n",
    )
    files = ORDER.run([source], tmp_path / "ordered").files
    quality = score_quality(files)
    assert quality.dimensions["consistency"].score < 100
    assert quality.dimensions["uniqueness"].score < 100
    assert quality.tabular is not None
    findings = {item.rule: item for item in quality.tabular.files[0].findings}
    assert findings["out_of_order"].rows == (2, 3)
    assert findings["duplicate_timestamp"].rows == (3, 4)
    assert all(item.column == "timestamp" for item in findings.values())


def test_stuck_and_range_rules_reduce_distribution_and_keep_interval_evidence(
    tmp_path: Path,
) -> None:
    """A sensor's constant interval and out-of-range sample remain separate reasons."""
    content = "timestamp,device_id,temperature\n" + "".join(
        f"{1700000000000 + index * 1000},A,{value}\n"
        for index, value in enumerate((20, 20, 20, 20, 20, 95, 21))
    )
    source = _file(tmp_path, content)
    files = ANOMALY.run(
        [source],
        tmp_path / "anomaly",
        {
            "value_columns": ["temperature"],
            "stuck_min_points": 5,
            "ranges": [{"column": "temperature", "minimum": 0.0, "maximum": 60.0}],
        },
    ).files
    quality = score_quality(files)
    assert quality.dimensions["distribution"].score < 100
    assert quality.tabular is not None
    evidence = quality.tabular.files[0]
    findings = {item.rule: item for item in evidence.findings}
    assert {"stuck_value", "out_of_range"} <= findings.keys()
    assert findings["stuck_value"].rows == (2, 3, 4, 5, 6)
    assert (findings["stuck_value"].start_ms, findings["stuck_value"].end_ms) == (
        1700000000000,
        1700000004000,
    )
    assert findings["out_of_range"].rows == (7,)
    assert evidence.anomaly_intervals >= 2
    assert all(item.column == "temperature" for item in findings.values())


def test_timestamp_and_unit_issues_reduce_consistency(tmp_path: Path) -> None:
    """Timezone and declared-unit mismatches survive normalization in typed summaries."""
    source = _file(
        tmp_path,
        "timestamp,device_id,temperature\n"
        "2026-10-01T00:00:00Z,A,20 C\n2026-10-01T08:00:01+08:00,A,70 F\n",
    )
    normalized = TIMESTAMP.run([source], tmp_path / "time").files
    checked = UNITS.run(
        normalized,
        tmp_path / "units",
        {"declarations": [{"column": "temperature", "unit": "C"}]},
    ).files
    quality = score_quality(checked)
    assert quality.dimensions["consistency"].score < 100
    assert quality.tabular is not None
    rules = {item.rule for item in quality.tabular.files[0].findings}
    assert "timezone_mixed" in rules
    assert rules & {"unit_mixed", "unit_mismatch"}


def test_pii_values_never_appear_in_quality_or_report(tmp_path: Path) -> None:
    """Contact findings expose column names and evidence rows without copying values."""
    source = _file(
        tmp_path,
        "id,phone,email\nA,13800138000,alice@example.com\nB,13800138001,bob@example.org\n",
    )
    files = PROFILE.run([source], tmp_path / "profile").files
    quality = score_quality(files)
    report = build_report({"name": "Generated contacts"}, quality)
    for output in (quality.model_dump_json(), report.model_dump_json()):
        assert "13800138000" not in output
        assert "alice@example.com" not in output
    assert quality.tabular is not None
    assert {column.name for column in quality.tabular.files[0].columns if column.pii_kinds} == {
        "phone",
        "email",
    }
    assert "suspected_pii" in report.body


def test_no_table_evidence_preserves_original_quality_and_report_shape(tmp_path: Path) -> None:
    """A CSV filename alone adds no inferred facts or extra report chapter."""
    source = _file(tmp_path, "id,value\nA,1\n")
    quality = score_quality([source])
    renamed = source.model_copy(update={"filename": "sample.txt", "modality": "text"})
    text_quality = score_quality([renamed])
    assert quality.total == text_quality.total == 100
    assert quality.tabular is None
    assert all(
        dimension.score == 100
        for key, dimension in quality.dimensions.items()
        if key != "annotation"
    )
    assert len(build_report({"name": "No profile"}, quality).chapters) == 6
    assert "tabular_score" not in quality.dimensions["completeness"].details


def test_empty_table_has_zero_completeness_and_an_explicit_report_reason(tmp_path: Path) -> None:
    """A header-only input cannot score as fully complete because bytes exist."""
    source = _file(tmp_path, "id,temperature\n")
    files = PROFILE.run([source], tmp_path / "profile").files
    quality = score_quality(files)
    report = build_report({"name": "Empty readings"}, quality)
    assert quality.dimensions["completeness"].score == 0
    assert any(issue.code == "empty_table" for issue in quality.issues)
    assert "Table contains no data rows" in report.body


def test_report_chapter_lists_columns_gap_duration_and_repairs(tmp_path: Path) -> None:
    """The additional chapter is assembled from saved aggregate evidence only."""
    source = _file(
        tmp_path,
        "timestamp,device_id,temperature\n1700000000000,A,20\n1700000003000,A,21\n",
    )
    files = GAPS.run([source], tmp_path / "gaps", {"expected_interval_ms": 1000}).files
    files = PROFILE.run(files, tmp_path / "profile").files
    quality = score_quality(files)
    report = build_report({"name": "Generated readings"}, quality)
    chapter = report.chapters[-1]
    assert len(report.chapters) == 7
    assert "Table and time-series profile" in chapter.title
    assert "timestamp: type=integer" in chapter.body
    assert "device_id: type=identifier" in chapter.body
    assert "temperature: type=integer" in chapter.body
    assert "anomaly intervals: 0" in chapter.body
    assert "2000 ms" in chapter.body
    assert "Repair:" in chapter.body
    assert "Recover missing samples" in chapter.body


def test_tabular_scores_average_files_without_fabricating_unprofiled_rows(tmp_path: Path) -> None:
    """A measured empty file and an unrelated file contribute independently."""
    source = _file(tmp_path, "id\n")
    empty = PROFILE.run([source], tmp_path / "profile").files[0]
    ordinary = _file(tmp_path, "id\nA\n", "ordinary.csv")
    assessment = assess_tables([empty, ordinary])
    assert len(assessment.files) == 1
    assert assessment.scores["completeness"] == 50


def test_long_issue_row_evidence_is_bounded_only_in_rendered_text(tmp_path: Path) -> None:
    """The report abbreviates long row lists but the typed evidence remains complete."""
    source = _file(tmp_path, "id,reading\n" + "".join(f"{index},\n" for index in range(20)))
    files = PROFILE.run([source], tmp_path / "profile").files
    quality = score_quality(files)
    report = build_report({"name": "Missing readings"}, quality)
    assert quality.tabular is not None
    assert len(quality.tabular.files[0].findings[0].rows) == 20
    assert "20 source rows" in report.chapters[-1].body
    assert "20 recorded" in next(
        issue.message for issue in quality.issues if issue.code == "null_values"
    )


def test_empty_manifest_has_no_table_assessment() -> None:
    """No input yields no inferred profile or fabricated column evidence."""
    assert assess_tables([]).files == ()
    assert score_quality([]).tabular is None
