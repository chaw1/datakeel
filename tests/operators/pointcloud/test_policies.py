# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Exercise batch unit suspicion and parameter policy continuity across operators."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from datakeel.operators.pointcloud import clean, downsample, preview, probe, unit_check
from datakeel.operators.pointcloud.io import dump_cloud
from tests.operators.pointcloud.helpers import make_cloud

if TYPE_CHECKING:
    from pathlib import Path

    from tests.operators.factories import FileFactory


def test_batch_unit_check_finds_small_millimeter_cloud_below_absolute_threshold(
    make_file: FileFactory,
    output_dir: Path,
) -> None:
    """A small object expressed in millimeters is suspicious relative to meter-scale peers."""
    sources = [
        make_file(
            dump_cloud(make_cloud(np.array([[0.0, 0.0, 0.0], [size, size, size]]))),
            f"scan-{index}.ply",
            "point-cloud",
        )
        for index, size in enumerate((0.5, 0.6, 500.0))
    ]
    result = unit_check.OPERATOR.run(sources, output_dir).files
    assert [file.metadata["pointcloud_probe"]["unit_suspected"] for file in result] == [
        False,
        False,
        True,
    ]
    assert result[-1].metadata["pointcloud_unit_check"]["reference_extent"] == 0.55
    cleaned = clean.OPERATOR.run([result[-1]], output_dir).files[0]
    assert cleaned.metadata["pointcloud_probe"]["unit_suspected"] is True
    assert cleaned.metadata["source_pointcloud_probe"]["unit_suspected"] is True


def test_measurement_policy_survives_preview_and_geometry_transforms(
    make_file: FileFactory,
    output_dir: Path,
) -> None:
    """Configured quality thresholds remain in force when subsequent operators refresh metadata."""
    cloud = make_cloud(np.array([[0.0, 0.0, 0.0], [15.0, 15.0, 15.0], [30.0, 30.0, 30.0]]))
    source = make_file(dump_cloud(cloud), "scan.ply", "point-cloud")
    measured = probe.OPERATOR.run(
        [source], output_dir, {"neighbors": 2, "distance_ratio": 3.0, "expected_max_extent": 20.0}
    ).files[0]
    displayed = preview.OPERATOR.run([measured], output_dir).files[0]
    assert displayed.metadata["pointcloud_probe"] == measured.metadata["pointcloud_probe"]
    transformed = downsample.OPERATOR.run([displayed], output_dir).files[0]
    assert (
        transformed.metadata["pointcloud_probe_params"]
        == measured.metadata["pointcloud_probe_params"]
    )
    assert transformed.metadata["pointcloud_probe"]["unit_suspected"] is True
    assert "pointcloud_preview" not in transformed.metadata


def test_explicit_reference_and_custom_ratio_produce_matching_scale_hint(
    make_file: FileFactory,
    output_dir: Path,
) -> None:
    """An explicit nondefault comparison ratio cannot emit a hard-coded millimeter hint."""
    source = make_file(
        dump_cloud(make_cloud(np.array([[0.0, 0.0, 0.0], [50.0, 50.0, 50.0]]))),
        "centimeters.ply",
        "point-cloud",
    )
    result = unit_check.OPERATOR.run(
        [source], output_dir, {"reference_extent": 0.5, "scale_ratio": 100.0}
    ).files[0]
    assert result.metadata["pointcloud_unit_check"]["suspected"] is True
    assert result.metadata["pointcloud_unit_check"]["suggested_scale"] == 0.01


def test_empty_unit_check_batch_produces_no_outputs(output_dir: Path) -> None:
    """Batch-relative scale estimation has a defined empty input behavior."""
    assert unit_check.OPERATOR.run([], output_dir).files == []
