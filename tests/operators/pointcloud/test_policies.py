# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Exercise unit suspicion, batch hints, policy continuity and per-file failure."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
import pytest

from datakeel.operators.pointcloud import (
    clean,
    downsample,
    outliers,
    preview,
    probe,
    unit_check,
)
from datakeel.operators.pointcloud.io import dump_cloud
from datakeel.quality.image_pointcloud import pointcloud_assessment
from tests.operators.pointcloud.helpers import make_cloud

if TYPE_CHECKING:
    from pathlib import Path

    from datakeel.core.models import FileItem
    from datakeel.operators.base import Operator
    from tests.operators.factories import FileFactory

HINT = "batch_extent_ratio_possible_unit_mismatch"


def _cloud(make_file: FileFactory, extent: float, name: str = "scan.ply") -> FileItem:
    corners = np.array([[0.0, 0.0, 0.0], [extent, extent, extent]])
    return make_file(dump_cloud(make_cloud(corners)), name, "point-cloud")


def _broken(make_file: FileFactory) -> FileItem:
    header = b"ply\nformat ascii 1.0\nelement vertex 9\nproperty float x\nend_header\n1 2\n"
    return make_file(header, "broken.ply", "point-cloud")


def test_mixed_scale_batch_gets_a_hint_not_a_defect(
    make_file: FileFactory, output_dir: Path
) -> None:
    """A small part in millimeters among meter scans is noted, never judged wrong."""
    sources = [_cloud(make_file, size, f"scan-{size}.ply") for size in (0.5, 0.6, 500.0)]
    result = unit_check.OPERATOR.run(sources, output_dir).files
    probes = [file.metadata["pointcloud_probe"] for file in result]
    assert [item["unit_suspected"] for item in probes] == [False, False, False]
    assert [item["unit_hint"] for item in probes] == [None, None, HINT]
    checked = result[-1].metadata["pointcloud_unit_check"]
    assert checked["reference_extent"] == 0.55
    assert checked["suggested_scale"] == 0.001
    assert checked["coordinates_changed"] is False
    assessed = pointcloud_assessment(result[-1])
    assert assessed.consistency == 1
    assert [(issue["code"], issue["severity"]) for issue in assessed.issues] == [
        ("pointcloud_unit_hint", "info")
    ]
    cleaned = clean.OPERATOR.run([result[-1]], output_dir).files[0]
    assert cleaned.metadata["pointcloud_probe"]["unit_hint"] == HINT
    assert cleaned.metadata["source_pointcloud_probe"]["unit_hint"] == HINT


def test_extent_beyond_the_sensor_maximum_is_suspected(
    make_file: FileFactory, output_dir: Path
) -> None:
    """Only an implausible extent for the declared form is a unit defect, noted once."""
    sources = [_cloud(make_file, size, f"part-{size}.ply") for size in (0.5, 0.6, 300.0)]
    measured = probe.OPERATOR.run(sources, output_dir, {"sensor": "object"}).files
    assert measured[-1].metadata["pointcloud_probe"]["unit_suspected"] is True
    checked = unit_check.OPERATOR.run(measured, output_dir).files
    assert [file.metadata["pointcloud_unit_check"]["suspected"] for file in checked] == [
        False,
        False,
        True,
    ]
    assert checked[-1].metadata["pointcloud_unit_check"]["reference_extent"] == 0.55
    assert checked[-1].metadata["pointcloud_unit_check"]["suggested_scale"] == 0.001
    assert checked[-1].metadata["pointcloud_probe"]["unit_hint"] is None
    assessed = pointcloud_assessment(checked[-1])
    assert assessed.consistency == pytest.approx(0.2)
    assert [issue["code"] for issue in assessed.issues] == ["pointcloud_unit"]
    plain = probe.OPERATOR.run(sources[-1:], output_dir).files[0]
    assert plain.metadata["pointcloud_probe"]["unit_suspected"] is False


def test_measurement_policy_survives_preview_and_geometry_transforms(
    make_file: FileFactory, output_dir: Path
) -> None:
    """Configured thresholds remain in force when later operators refresh metadata."""
    cloud = make_cloud(np.array([[0.0, 0.0, 0.0], [15.0, 15.0, 15.0], [30.0, 30.0, 30.0]]))
    source = make_file(dump_cloud(cloud), "scan.ply", "point-cloud")
    params = {"neighbors": 2, "local_ratio": 4.0, "expected_max_extent": 20.0}
    measured = probe.OPERATOR.run([source], output_dir, params).files[0]
    displayed = preview.OPERATOR.run([measured], output_dir).files[0]
    assert displayed.metadata["pointcloud_probe"] == measured.metadata["pointcloud_probe"]
    transformed = downsample.OPERATOR.run([displayed], output_dir).files[0]
    recorded = transformed.metadata["pointcloud_probe_params"]
    assert recorded == measured.metadata["pointcloud_probe_params"]
    assert recorded["local_ratio"] == 4.0
    assert transformed.metadata["pointcloud_probe"]["unit_suspected"] is True
    assert "pointcloud_preview" not in transformed.metadata


@pytest.mark.parametrize(
    ("extent", "reference", "ratio", "expected"),
    [(50.0, 0.5, 100.0, 0.01), (0.005, 0.5, 100.0, 100.0), (0.5, 0.5, 100.0, None)],
)
def test_explicit_reference_and_ratio_give_a_matching_scale_in_both_directions(
    make_file: FileFactory,
    output_dir: Path,
    extent: float,
    reference: float,
    ratio: float,
    expected: float | None,
) -> None:
    """A hint names the factor toward the reference; a matching extent gets none."""
    result = unit_check.OPERATOR.run(
        [_cloud(make_file, extent)],
        output_dir,
        {"reference_extent": reference, "scale_ratio": ratio},
    ).files[0]
    checked = result.metadata["pointcloud_unit_check"]
    assert checked["suspected"] is False
    assert checked["hint"] == (HINT if expected else None)
    assert checked["suggested_scale"] == expected


def test_empty_unit_check_batch_produces_no_outputs(output_dir: Path) -> None:
    """Batch-relative scale estimation has a defined empty input behavior."""
    result = unit_check.OPERATOR.run([], output_dir)
    assert result.files == []
    assert result.quality["partial"] is False


OPERATORS = [probe.OPERATOR, clean.OPERATOR, downsample.OPERATOR, outliers.OPERATOR]


@pytest.mark.parametrize("operator", [*OPERATORS, preview.OPERATOR, unit_check.OPERATOR])
def test_one_unreadable_file_leaves_the_rest_of_the_batch_processed(
    make_file: FileFactory, output_dir: Path, operator: Operator
) -> None:
    """The broken file keeps its reason; the others are processed and the run is partial."""
    good = [_cloud(make_file, 1.0, "first.ply"), _cloud(make_file, 1.2, "second.ply")]
    broken = _broken(make_file)
    result = operator.run([good[0], broken, good[1]], output_dir)
    assert len(result.files) == 3
    assert result.files[1].id == broken.id
    failure = result.files[1].metadata.get("pointcloud_error")
    assert isinstance(failure, dict)
    assert failure["operator"] == operator.manifest.id
    assert "Malformed or truncated" in failure["reason"]
    assert result.quality["partial"] is True
    assert result.quality["failed_count"] == 1
    assert result.quality["failed_files"][0]["filename"].endswith("broken.ply")
    assert [issue["code"] for issue in result.quality["issues"]] == ["pointcloud_unreadable"]
    assert all("pointcloud_error" not in result.files[index].metadata for index in (0, 2))
    clean_run = operator.run(good, output_dir)
    assert clean_run.quality["partial"] is False
    assert clean_run.quality["failed_count"] == 0


@pytest.mark.parametrize("operator", OPERATORS)
def test_later_steps_skip_a_failed_file_and_keep_the_first_reason(
    make_file: FileFactory, output_dir: Path, operator: Operator
) -> None:
    """A file that failed earlier is not read again, and its original reason survives."""
    failed = probe.OPERATOR.run([_broken(make_file)], output_dir).files[0]
    passed = operator.run([failed], output_dir)
    assert passed.files == [failed]
    assert passed.quality["failed_files"][0]["operator"] == "pointcloud.probe"
    assessed = pointcloud_assessment(passed.files[0])
    assert assessed.completeness == 0
    assert [(issue["code"], issue["severity"]) for issue in assessed.issues] == [
        ("pointcloud_unreadable", "error")
    ]
