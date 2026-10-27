# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Verify geometric transforms, metadata attribution and preview side artifacts."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import pytest
from PIL import Image
from pydantic import ValidationError as PydanticValidationError

from datakeel.core.errors import ValidationError
from datakeel.operators.pointcloud import clean, downsample, outliers, preview, probe, unit_check
from datakeel.operators.pointcloud.io import dump_cloud, load_cloud
from datakeel.operators.pointcloud.models import (
    CleanParams,
    DownsampleParams,
    OutlierParams,
    PreviewParams,
    ProbeParams,
    UnitCheckParams,
)
from tests.operators.pointcloud.helpers import make_cloud

if TYPE_CHECKING:
    from tests.operators.factories import FileFactory


def test_probe_measures_finite_box_invalid_rows_and_density() -> None:
    """Finite coordinates alone determine bounds and density; invalid counts are per row."""
    cloud = make_cloud(
        np.array([[0.0, 0.0, 0.0], [2.0, 2.0, 2.0], [np.nan, 0.0, 0.0], [0.0, np.inf, 0.0]])
    )
    result = probe.inspect_cloud(cloud)
    assert result.point_count == 4
    assert result.bounding_box is not None
    assert result.bounding_box.min == (0, 0, 0)
    assert result.bounding_box.max == (2, 2, 2)
    assert result.density == 0.25
    assert result.nan_count == result.inf_count == 1
    assert result.invalid_count == 2
    assert result.invalid_ratio == 0.5


def test_probe_handles_empty_and_degenerate_clouds() -> None:
    """Empty clouds report no box; flat geometry has a finite source-unit density."""
    empty = probe.inspect_cloud(make_cloud(np.empty((0, 3))))
    assert empty.bounding_box is None
    assert empty.density == empty.invalid_ratio == empty.outlier_ratio == 0
    plane = probe.inspect_cloud(make_cloud(np.array([[0.0, 0.0, 0.0], [2.0, 2.0, 0.0]])))
    assert plane.density == 0.5


def test_probe_main_body_ignores_distant_strays_for_density_and_units() -> None:
    """A few far points widen coverage but neither dilute density nor imply millimeters."""
    rng = np.random.default_rng(1812)
    grid = np.stack(np.meshgrid(*(np.linspace(0, 4, 20),) * 3), axis=-1).reshape(-1, 3)
    strays = rng.uniform(-3000, 3000, (40, 3))
    dense = probe.inspect_cloud(make_cloud(grid))
    mixed = probe.inspect_cloud(make_cloud(np.vstack((grid, strays))))
    assert dense.outlier_ratio == 0
    assert mixed.outlier_ratio == pytest.approx(40 / 8040)
    assert mixed.bounding_box is not None
    assert max(mixed.bounding_box.max) > 1000
    assert mixed.body_extent == dense.body_extent == 4
    assert mixed.density == pytest.approx(dense.density)
    assert not mixed.unit_suspected


def test_clean_removes_invalid_and_clips_inclusive_bounds_preserving_fields(
    make_file: FileFactory,
    output_dir: Path,
) -> None:
    """Coordinate filtering selects entire source rows rather than rebuilding xyz only."""
    cloud = make_cloud(
        np.array([[0.0, 0.0, 0.0], [1.0, 1.0, 1.0], [2.0, 2.0, 2.0], [np.nan, 0.0, 0.0]])
    )
    source = make_file(dump_cloud(cloud), "scan.ply", "point-cloud")
    before = probe.OPERATOR.run([source], output_dir).files[0]
    output = clean.OPERATOR.run(
        [before], output_dir, {"min_bound": [0.0, 0.0, 0.0], "max_bound": [1.0, 1.0, 1.0]}
    ).files[0]
    np.testing.assert_array_equal(load_cloud(Path(output.path)).data, cloud.data[:2])
    assert output.id != source.id
    assert output.metadata["source_file_id"] == source.id
    assert output.metadata["pointcloud_probe"]["point_count"] == 2
    assert output.metadata["source_pointcloud_probe"]["invalid_count"] == 1


def test_clean_can_retain_invalid_rows_when_explicitly_requested(
    make_file: FileFactory,
    output_dir: Path,
) -> None:
    """The explicit preserve mode remains deterministic for workflows needing raw records."""
    cloud = make_cloud(np.array([[np.nan, 0.0, 0.0], [1.0, 2.0, 3.0]]))
    source = make_file(dump_cloud(cloud), "scan.ply", "point-cloud")
    result = clean.OPERATOR.run([source], output_dir, {"remove_invalid": False})
    assert len(load_cloud(Path(result.files[0].path)).data) == 2


def test_downsample_keeps_first_record_per_voxel_and_stable_input_order(
    make_file: FileFactory,
    output_dir: Path,
) -> None:
    """Duplicates collapse without corrupting labels, negative coordinates or record order."""
    cloud = make_cloud(
        np.array(
            [
                [1.1, 1.1, 1.1],
                [0.1, 0.1, 0.1],
                [0.9, 0.9, 0.9],
                [-0.1, -0.1, -0.1],
                [-0.9, -0.9, -0.9],
                [np.inf, 0.0, 0.0],
            ]
        )
    )
    source = make_file(dump_cloud(cloud), "scan.ply", "point-cloud")
    result = downsample.OPERATOR.run([source], output_dir, {"voxel_size": 1.0}).files[0]
    np.testing.assert_array_equal(load_cloud(Path(result.path)).data, cloud.data[[0, 1, 3]])
    assert result.metadata["pointcloud_processing"]["removed_count"] == 3


def test_downsample_handles_empty_cloud_and_rejects_grid_overflow() -> None:
    """Invalid grids fail explicitly instead of wrapping distinct voxels into one."""
    assert not len(downsample.voxel_indices(np.array([[np.nan, 0.0, 0.0]]), 1.0))
    with pytest.raises(ValidationError, match="voxel grid"):
        downsample.voxel_indices(np.array([[1e30, 0.0, 0.0]]), 0.1)


def test_statistical_outliers_remove_distant_points_and_preserve_labels(
    make_file: FileFactory,
    output_dir: Path,
) -> None:
    """Sparse distant points have larger mean kNN distances than a compact dense cluster."""
    rng = np.random.default_rng(101)
    xyz = np.vstack((rng.normal(0, 0.05, (200, 3)), [[30.0, 30.0, 30.0], [np.nan, 0.0, 0.0]]))
    cloud = make_cloud(xyz)
    source = make_file(dump_cloud(cloud), "scan.ply", "point-cloud")
    result = outliers.OPERATOR.run([source], output_dir).files[0]
    np.testing.assert_array_equal(load_cloud(Path(result.path)).data, cloud.data[:200])
    assert result.metadata["pointcloud_processing"]["removed_count"] == 2


def test_unit_check_flags_millimeter_extent_but_never_changes_coordinates(
    make_file: FileFactory,
    output_dir: Path,
) -> None:
    """Unit suspicion is an explicit heuristic whose threshold users can override."""
    cloud = make_cloud(np.array([[0.0, 0.0, 0.0], [12000.0, 6000.0, 3000.0]]))
    source = make_file(dump_cloud(cloud), "millimeters.ply", "point-cloud")
    result = unit_check.OPERATOR.run([source], output_dir).files[0]
    assert result.id == source.id
    assert Path(result.path).read_bytes() == Path(source.path).read_bytes()
    assert result.metadata["pointcloud_unit_check"]["suspected"] is True
    assert result.metadata["pointcloud_unit_check"]["suggested_scale"] == 0.001
    overridden = unit_check.OPERATOR.run([source], output_dir, {"expected_max_extent": 20000.0})
    assert overridden.files[0].metadata["pointcloud_probe"]["unit_suspected"] is False


@pytest.mark.parametrize("color_by", ["height", "intensity"])
def test_preview_retains_cloud_slot_and_emits_deterministic_png(
    make_file: FileFactory,
    output_dir: Path,
    color_by: str,
) -> None:
    """A side image must not replace the source point-cloud file in downstream slots."""
    cloud = make_cloud(np.random.default_rng(3).normal(size=(200, 3)))
    source = make_file(dump_cloud(cloud), "scan.ply", "point-cloud")
    result = preview.OPERATOR.run([source], output_dir, {"size": 64, "color_by": color_by}).files[0]
    reference = result.metadata["pointcloud_preview"]
    assert result.id == source.id
    assert result.modality == "point-cloud"
    assert result.path == source.path
    content = Path(reference["path"]).read_bytes()
    assert Image.open(BytesIO(content)).size == (64, 64)
    repeated = preview.OPERATOR.run([source], output_dir, {"size": 64, "color_by": color_by})
    assert Path(repeated.files[0].metadata["pointcloud_preview"]["path"]).read_bytes() == content


def test_preview_raster_handles_empty_cloud() -> None:
    """Empty finite geometry still yields a correctly sized deterministic background."""
    raster = preview.render_preview(make_cloud(np.empty((0, 3))), PreviewParams(size=32))
    assert raster.shape == (32, 32, 3)
    assert np.unique(raster.reshape(-1, 3), axis=0).shape == (1, 3)


@pytest.mark.parametrize(
    "params_type",
    [ProbeParams, CleanParams, DownsampleParams, OutlierParams, UnitCheckParams, PreviewParams],
)
def test_operator_parameters_reject_undeclared_fields(params_type: type[ProbeParams]) -> None:
    """All six operators derive strict schemas rather than accepting silent typo defaults."""
    with pytest.raises(PydanticValidationError):
        params_type.model_validate({"unexpected_parameter": 1})


def test_inverted_clean_bounds_fail_before_execution() -> None:
    """Reject impossible crop parameters at validation time."""
    with pytest.raises(PydanticValidationError, match="min_bound"):
        CleanParams(min_bound=(2.0, 0.0, 0.0), max_bound=(1.0, 1.0, 1.0))
