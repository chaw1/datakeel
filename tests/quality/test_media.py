# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Recorded media signals change quality, reporting and per-file cleanup selection."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from datakeel.core.models import FileItem
from datakeel.quality import build_report, score_quality
from datakeel.quality.media import assess_file
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
        ("density", 0.2, "distribution", 20, "pointcloud_sparse"),
        ("unit_suspected", True, "consistency", 20, "pointcloud_unit"),
    ],
)
def test_pointcloud_signals_have_specific_dimension_penalties(
    signal: str, value: JsonValue, dimension: str, expected: float, code: str
) -> None:
    """Each independently measured problem has its own reason and bounded score."""
    probe: dict[str, JsonValue] = {
        "point_count": 100,
        "density": 10,
        "invalid_ratio": 0,
        "outlier_ratio": 0,
        "unit_suspected": False,
        "unit_reason": "possible millimeters",
        signal: value,
    }
    quality = score_quality([_file("point-cloud", pointcloud_probe=probe)])
    assert quality.dimensions[dimension].score == expected
    assert any(issue.code == code for issue in quality.issues)
    assert "点云 / Point clouds" in build_report({"name": "generated"}, quality).body


def test_clean_probe_has_no_pointcloud_issues_and_full_score() -> None:
    """A dense, finite, correctly scaled scan without outliers is not penalized."""
    probe: dict[str, JsonValue] = {
        "point_count": 5000,
        "density": 40,
        "invalid_ratio": 0,
        "outlier_ratio": 0,
        "unit_suspected": False,
    }
    file = _file("point-cloud", pointcloud_probe=probe)
    assert assess_file(file).score == 100
    assert not [issue for issue in score_quality([file]).issues if issue.code.startswith("point")]


def test_sparse_threshold_follows_recorded_policy_and_yields_to_unit_suspicion() -> None:
    """The density minimum is configurable; suspect units make density incomparable."""
    probe: dict[str, JsonValue] = {"point_count": 100, "density": 5, "unit_suspected": False}
    strict = _file(
        "point-cloud", pointcloud_probe=probe, pointcloud_probe_params={"min_density": 20}
    )
    assessment = assess_file(strict)
    assert assessment.distribution == 0.25
    assert [issue.code for issue in assessment.issues] == ["pointcloud_sparse"]
    assert "below minimum 20" in assessment.issues[0].message
    lenient = _file(
        "point-cloud", pointcloud_probe=probe, pointcloud_probe_params={"min_density": 0}
    )
    assert assess_file(lenient).issues == []
    scaled = _file(
        "point-cloud",
        pointcloud_probe={"point_count": 100, "density": 1e-7, "unit_suspected": True},
    )
    assert [issue.code for issue in assess_file(scaled).issues] == ["pointcloud_unit"]
    assert assess_file(scaled).distribution == 1


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
