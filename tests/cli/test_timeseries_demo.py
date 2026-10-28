# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Exercise generated sensor ingestion, durable execution, catalog actions and reports."""

from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from datakeel.ask.service import ask_data
from datakeel.cli import parser
from datakeel.cli.timeseries_demo import run_timeseries_demo
from datakeel.core.ask_models import AskRequest
from datakeel.core.catalog_models import CatalogQuery
from datakeel.core.models import FileItem
from datakeel.operators.timeseries.models import ColumnRange, UnitDeclaration
from datakeel.pipeline import run_pipeline
from datakeel.pipeline.tabular import timeseries_pipeline
from datakeel.quality import score_quality
from datakeel.sample_timeseries import WEEK_SAMPLES, generate_sensor_samples
from datakeel.storage.catalog_queries import read_objects
from datakeel.storage.dataset_service import list_versions, task_artifacts
from datakeel.storage.governance_service import get_quality, get_report

if TYPE_CHECKING:
    from datakeel.storage.database import Database


def test_demo_publishes_all_planted_problems_through_durable_actions(
    db: Database,
    tmp_path: Path,
) -> None:
    """Require the week-long fixture's measurements to survive storage and action publication."""
    result = run_timeseries_demo(db, tmp_path / "demo")
    assert result.state == "COMPLETED"
    versions = list_versions(db, result.dataset_id)
    assert len(versions) == 2
    assert len(task_artifacts(db, result.task_id)) == 3
    quality = get_quality(db, result.dataset_id)
    assert quality.tabular is not None
    rules = Counter(finding.rule for file in quality.tabular.files for finding in file.findings)
    assert {
        "timezone_mixed",
        "out_of_order",
        "sampling_gap",
        "stuck_value",
        "robust_z",
        "out_of_range",
        "unit_mismatch",
        "suspected_pii",
    } <= rules.keys()
    assert rules["sampling_gap"] == 2
    assert rules["stuck_value"] == 1
    assert rules["robust_z"] >= 3
    assert rules["out_of_range"] == 3
    assert rules["unit_mismatch"] == 12
    assert sum(file.total_gap_ms for file in quality.tabular.files) == 10_800_000
    assert 0 < quality.total < 100
    tables = read_objects(db, CatalogQuery(kind="table", source_id=result.catalog_source))
    assert tables.total == 3
    assert all(item.properties.root.get("table_profile") for item in tables.items)
    report = get_report(db, result.dataset_id)
    assert len(report.chapters) == 7
    for term in ("temperature", "contact_phone", "gas_flow", "stuck_value", "unit_mismatch"):
        assert term in report.body
    assert "total missing-sample duration" in report.body
    assert json.loads(result.evidence_path.read_text())["total"] == quality.total
    assert result.report_path.read_text().strip() == report.body


def test_clean_generated_week_has_at_most_two_unplanted_detections(tmp_path: Path) -> None:
    """Use a separate unmodified week to measure false alarms, rather than suppressing findings."""
    samples = generate_sensor_samples(tmp_path / "clean", faults=False)
    files = [
        FileItem(
            id=str(index),
            path=str(path),
            filename=path.name,
            modality="table",
            sha256=str(index).zfill(64),
            size=path.stat().st_size,
        )
        for index, path in enumerate(samples.paths)
    ]
    outputs = run_pipeline(
        files,
        tmp_path / "output",
        timeseries_pipeline(
            interval_ms=samples.interval_ms,
            values=("temperature", "fan_speed"),
            ranges=(ColumnRange(column="temperature", minimum=-20, maximum=150),),
            units=(UnitDeclaration(column="gas_flow", unit="L/min", minimum=0, maximum=10),),
        ),
    )
    quality = score_quality(outputs)
    assert quality.tabular is not None
    unplanted = [
        finding
        for file in quality.tabular.files
        for finding in file.findings
        if finding.rule != "suspected_pii"
    ]
    assert len(unplanted) <= 2, unplanted
    assert all(file.row_count == WEEK_SAMPLES for file in quality.tabular.files)
    assert sum(file.total_gap_ms for file in quality.tabular.files) == 0
    assert sum(file.anomaly_intervals for file in quality.tabular.files) == 0


def test_cli_registers_one_shot_sensor_demo() -> None:
    """Expose the generated scenario without starting a server or a model provider."""
    args = parser().parse_args(["timeseries-demo", "--output", "reports"])
    assert args.output == Path("reports")


@pytest.mark.parametrize("faults", [False, True])
def test_sensor_generator_is_byte_deterministic(tmp_path: Path, *, faults: bool) -> None:
    """Make evidence reproducible across reruns in distinct directories."""
    first = generate_sensor_samples(tmp_path / "first", faults=faults)
    second = generate_sensor_samples(tmp_path / "second", faults=faults)
    assert [path.read_bytes() for path in first.paths] == [
        path.read_bytes() for path in second.paths
    ]


def test_planted_week_detections_stay_inside_known_fault_regions(tmp_path: Path) -> None:
    """Count alarms outside the planted source regions independently of the detection rules."""
    samples = generate_sensor_samples(tmp_path / "faults")
    files = [
        FileItem(
            id=str(index),
            path=str(path),
            filename=path.name,
            modality="table",
            size=path.stat().st_size,
        )
        for index, path in enumerate(samples.paths)
    ]
    outputs = run_pipeline(
        files,
        tmp_path / "output",
        timeseries_pipeline(
            interval_ms=samples.interval_ms,
            values=("temperature", "fan_speed"),
            ranges=(ColumnRange(column="temperature", minimum=-20, maximum=150),),
            units=(UnitDeclaration(column="gas_flow", unit="L/min", minimum=0, maximum=10),),
        ),
    )
    quality = score_quality(outputs)
    assert quality.tabular is not None
    allowed = {
        ("kitchen-01.csv", "timezone_mixed"): set(range(120, 180)),
        ("kitchen-01.csv", "out_of_order"): set(range(200, 212)),
        ("kitchen-01.csv", "sampling_gap"): {999, 1012},
        ("kitchen-01.csv", "robust_z"): {310, 810, 1510},
        ("kitchen-01.csv", "out_of_range"): {310, 810, 1510},
        ("kitchen-02.csv", "sampling_gap"): {1299, 1324},
        ("kitchen-02.csv", "stuck_value"): set(range(500, 548)),
        ("kitchen-03.csv", "unit_mismatch"): set(range(900, 912)),
    }
    source_indices: dict[str, dict[int, int]] = {}
    origin = datetime(2026, 1, 5, tzinfo=UTC)
    for path in samples.paths:
        with path.open(newline="") as stream:
            rows = list(csv.DictReader(stream))
        source_indices[path.name] = {
            line: int((datetime.fromisoformat(row["timestamp"]) - origin).total_seconds() / 300)
            for line, row in enumerate(rows, 2)
        }
    false_alarms = []
    detected_spikes: set[int] = set()
    for file in quality.tabular.files:
        for finding in file.findings:
            if finding.rule == "suspected_pii":
                continue
            actual = {source_indices[file.filename][row] for row in finding.rows}
            if file.filename == "kitchen-01.csv" and finding.rule == "robust_z":
                detected_spikes.update(actual & {310, 810, 1510})
            if not actual <= allowed.get((file.filename, finding.rule), set()):
                false_alarms.append(finding)
    assert detected_spikes == {310, 810, 1510}
    assert len(false_alarms) <= 2, false_alarms


def test_demo_answers_gap_ranking_from_original_source_evidence(
    db: Database,
    tmp_path: Path,
) -> None:
    """Connect the real generated scenario to persisted question evidence without a model."""
    result = run_timeseries_demo(db, tmp_path / "question-demo")
    answer = ask_data(
        db,
        AskRequest(
            question="哪台设备的温度数据断档最多",
            subject_id=result.dataset_id,
        ),
    )
    assert answer.status == "answered"
    assert answer.answer_kind == "profile"
    assert answer.sql is None
    assert answer.profile is not None
    assert answer.profile.sort_by == "total_gap_ms"
    assert [(rank.device, rank.total_gap_ms) for rank in answer.profile.ranking] == [
        ("kitchen-02", 7_200_000),
        ("kitchen-01", 3_600_000),
    ]
    versions = list_versions(db, result.dataset_id)
    evidence = answer.profile.ranking[0].evidence[0]
    assert evidence.source_version_id == versions[0].id
    assert evidence.version_id == versions[-1].id
    assert evidence.file_id != evidence.source_file_id
    assert evidence.row_coordinates == "original_source"
