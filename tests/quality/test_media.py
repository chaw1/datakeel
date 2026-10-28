# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Recorded media signals change quality, reporting and per-file cleanup selection."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from datakeel.core.models import FileItem
from datakeel.operators.pointcloud.models import ProbeParams
from datakeel.quality import build_report, score_quality
from datakeel.quality.media import DEFAULT_MAX_OUTLIER_RATIO, assess_file
from datakeel.storage.database import DatasetRow
from datakeel.storage.object_projection import file_quality

if TYPE_CHECKING:
    from pydantic import JsonValue


def _file(modality: str, **metadata: JsonValue) -> FileItem:
    return FileItem(
        path="unreadable-source",
        filename="generated.ply" if modality == "point-cloud" else "generated.png",
        modality=modality,
        size=100,
        sha256="a" * 64,
        metadata=metadata,
    )


def test_image_scores_feed_completeness_report_and_cleanup() -> None:
    """A failed noise check is visible and selectable without rereading image bytes."""
    file = _file(
        "image",
        image_quality={
            "width": 512,
            "height": 512,
            "overall_score": 18.0,
            "checks": {"noise": {"score": 18.0, "failed": True, "reason": "sigma 28 > 12"}},
        },
    )
    quality = score_quality([file])
    assert quality.dimensions["completeness"].score == 18
    assert any(item.code == "image_noise" and "sigma 28" in item.message for item in quality.issues)
    assert file_quality(file, DatasetRow(name="generated", quality_config={})) == 18
    report = build_report({"name": "generated"}, quality)
    assert "图片质量 / Image quality" in report.body
    assert "sigma 28" in report.body


@pytest.mark.parametrize(
    ("signal", "value", "dimension", "expected", "code"),
    [
        ("invalid_ratio", 0.25, "completeness", 75, "pointcloud_invalid_ratio"),
        ("outlier_ratio", 0.4, "distribution", 60, "pointcloud_outlier_ratio"),
        ("relative_spacing", 0.05, "distribution", 20, "pointcloud_sparse"),
        ("unit_suspected", True, "consistency", 20, "pointcloud_unit"),
    ],
)
def test_pointcloud_signals_have_specific_dimension_penalties(
    signal: str, value: JsonValue, dimension: str, expected: float, code: str
) -> None:
    """Each independently measured problem has its own reason and bounded score."""
    probe: dict[str, JsonValue] = {
        "point_count": 100,
        "invalid_ratio": 0,
        "outlier_ratio": 0,
        "relative_spacing": 0.001,
        "spacing_limit": 0.01,
        "sparse_penalized": True,
        "unit_suspected": False,
        "unit_reason": "possible millimeters",
        signal: value,
    }
    quality = score_quality([_file("point-cloud", pointcloud_probe=probe)])
    assert quality.dimensions[dimension].score == expected
    assert any(issue.code == code for issue in quality.issues)
    assert "点云 / Point clouds" in build_report({"name": "generated"}, quality).body


def test_clean_probe_has_no_pointcloud_issues_and_full_score() -> None:
    """A dense, finite, correctly scaled scan with a few outliers below the limit is clean."""
    probe: dict[str, JsonValue] = {
        "point_count": 5000,
        "invalid_ratio": 0,
        "outlier_ratio": 0.0004,
        "relative_spacing": 0.002,
        "spacing_limit": 0.01,
        "sparse_penalized": True,
        "unit_suspected": False,
    }
    file = _file("point-cloud", pointcloud_probe=probe)
    assert assess_file(file).score == 100
    assert not [issue for issue in score_quality([file]).issues if issue.code.startswith("point")]


def _outliers(ratio: float, low: float, limit: float | None = None) -> FileItem:
    probe: dict[str, JsonValue] = {
        "point_count": 2_000_000,
        "outlier_ratio": ratio,
        "outlier_ci_low": low,
        "outlier_ci_high": ratio * 2 - low,
        "outlier_sampled": True,
        "outlier_sample_count": 500_000,
        "isolated_count": 700,
        "clustered_count": 120,
    }
    policy: dict[str, JsonValue] = {} if limit is None else {"max_outlier_ratio": limit}
    return _file("point-cloud", pointcloud_probe=probe, pointcloud_probe_params=policy)


def test_outlier_issue_needs_the_lower_confidence_bound_above_the_file_limit() -> None:
    """A sampled ratio within sampling error of the limit is not reported; a clear excess is."""
    assert ProbeParams().max_outlier_ratio == DEFAULT_MAX_OUTLIER_RATIO
    uncertain = assess_file(_outliers(0.0009, 0.0006))
    assert uncertain.issues == []
    assert uncertain.distribution == 1
    clear = assess_file(_outliers(0.002, 0.0018))
    assert [issue.code for issue in clear.issues] == ["pointcloud_outlier_ratio"]
    assert clear.distribution == pytest.approx(0.998)
    message = clear.issues[0].message
    assert "0.180%-0.220%" in message
    assert "500000 sampled points" in message
    assert "700 isolated, 120 in separated clusters" in message
    assert "limit 0.070%" in message
    assert assess_file(_outliers(0.002, 0.0018, limit=0.01)).issues == []
    full = _outliers(0.001, 0.001)
    full.metadata["pointcloud_probe"]["outlier_sampled"] = False  # type: ignore[index]
    assert "all 500000 finite points" in assess_file(full).issues[0].message


def test_sparse_coverage_is_a_hint_without_a_sensor_and_skipped_for_doubtful_units() -> None:
    """Relative spacing is penalized for declared forms only; doubtful units are not sparse."""
    probe: dict[str, JsonValue] = {
        "point_count": 100,
        "relative_spacing": 0.04,
        "spacing_limit": 0.01,
        "sparse_penalized": True,
        "sensor": "depth_camera",
        "unit_suspected": False,
    }
    declared = assess_file(_file("point-cloud", pointcloud_probe=probe))
    assert declared.distribution == 0.25
    assert [issue.code for issue in declared.issues] == ["pointcloud_sparse"]
    assert "0.0400 of the main-body extent" in declared.issues[0].message
    assert "depth_camera limit 0.01" in declared.issues[0].message
    hint = assess_file(_file("point-cloud", pointcloud_probe={**probe, "sparse_penalized": False}))
    assert hint.distribution == 1
    assert [(issue.code, issue.severity) for issue in hint.issues] == [
        ("pointcloud_sparse_hint", "info")
    ]
    dense = assess_file(_file("point-cloud", pointcloud_probe={**probe, "relative_spacing": 0.01}))
    assert dense.issues == []
    doubtful = assess_file(_file("point-cloud", pointcloud_probe={**probe, "unit_suspected": True}))
    assert [issue.code for issue in doubtful.issues] == ["pointcloud_unit"]
    assert doubtful.distribution == 1
    assert doubtful.consistency == 0.2
    assert "unit in doubt" in doubtful.issues[0].message


def test_batch_unit_hint_is_information_without_penalty() -> None:
    """A thousandfold difference from the batch alone never lowers a score."""
    probe: dict[str, JsonValue] = {
        "point_count": 100,
        "body_extent": 0.2,
        "unit_suspected": False,
        "unit_hint": "batch_extent_ratio_possible_unit_mismatch",
    }
    policy: dict[str, JsonValue] = {"reference_extent": 200.0, "scale_ratio": 1000.0}
    assessment = assess_file(
        _file("point-cloud", pointcloud_probe=probe, pointcloud_probe_params=policy)
    )
    assert assessment.score == 100
    assert [(issue.code, issue.severity) for issue in assessment.issues] == [
        ("pointcloud_unit_hint", "info")
    ]
    assert "reference extent=200.0" in assessment.issues[0].message


def test_empty_point_cloud_scores_zero_with_a_reason() -> None:
    """A readable file with no points names why it scores zero instead of listing nothing."""
    probe: dict[str, JsonValue] = {
        "point_count": 0,
        "invalid_ratio": 0,
        "outlier_ratio": 0,
        "relative_spacing": 0,
        "spacing_limit": 0.01,
        "unit_suspected": False,
    }
    assessment = assess_file(_file("point-cloud", pointcloud_probe=probe))
    assert assessment.score == 0
    assert assessment.completeness == 0
    assert [(issue.code, issue.dimension) for issue in assessment.issues] == [
        ("pointcloud_empty", "completeness")
    ]
    assert "no points" in assessment.issues[0].message
    probe["point_count"] = 1
    assert all(
        issue.code != "pointcloud_empty"
        for issue in assess_file(_file("point-cloud", pointcloud_probe=probe)).issues
    )


def test_unreadable_point_cloud_is_an_error_with_its_reason() -> None:
    """A file an operator could not read scores zero completeness and names the operator."""
    file = _file(
        "point-cloud",
        pointcloud_error={"operator": "pointcloud.probe", "reason": "ValidationError: bad header"},
    )
    assessment = assess_file(file)
    assert assessment.completeness == 0
    assert assessment.score == 0
    assert [(issue.code, issue.severity) for issue in assessment.issues] == [
        ("pointcloud_unreadable", "error")
    ]
    assert "pointcloud.probe could not process the file" in assessment.issues[0].message
    assert "bad header" in assessment.issues[0].message


def test_cleaned_scan_report_preserves_original_defects() -> None:
    """A corrected current score does not erase the original scan observations."""
    file = _file(
        "point-cloud",
        pointcloud_probe={"point_count": 90, "density": 10, "invalid_ratio": 0},
        source_pointcloud_probe={"point_count": 100, "invalid_ratio": 0.1, "nan_count": 10},
    )
    assert score_quality([file]).dimensions["completeness"].score == 100
    report = build_report({"name": "generated"}, score_quality([file]))
    assert "Original scan observations (before cleanup)" in report.body
    assert '"nan_count": 10' in report.body


@pytest.mark.parametrize("score", [-20, 130, float("nan"), "invalid", True])
def test_invalid_or_extreme_scores_are_bounded(score: object) -> None:
    """Legacy malformed metadata never introduces a nonfinite aggregate score."""
    file = _file("image")
    file.metadata["image_quality"] = {"overall_score": score}
    assert 0 <= assess_file(file).score <= 100
