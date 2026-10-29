# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Independent wire fixtures and geometry challenges for point-cloud integration."""

from __future__ import annotations

import struct
from typing import TYPE_CHECKING

import numpy as np
import pytest

from datakeel.operators import REGISTRY
from datakeel.operators.pointcloud.io import dump_cloud, load_cloud
from datakeel.operators.pointcloud.models import StatisticalParams
from datakeel.operators.pointcloud.statistics import outlier_mask
from datakeel.quality import score_quality
from datakeel.quality.image_pointcloud import assess_file
from datakeel.storage.database import DatasetRow
from datakeel.storage.object_projection import file_quality

if TYPE_CHECKING:
    from pathlib import Path

    from datakeel.core.models import FileItem
    from tests.operators.factories import FileFactory


def _cloud(make_file: FileFactory, rows: list[tuple[float, float, float]]) -> FileItem:
    header = (
        "ply\nformat ascii 1.0\nelement vertex "
        f"{len(rows)}\nproperty double x\nproperty double y\nproperty double z\nend_header\n"
    )
    body = "".join(f"{x:.17g} {y:.17g} {z:.17g}\n" for x, y, z in rows)
    return make_file(header + body, "independent.ply", "point-cloud")


@pytest.mark.parametrize(
    ("format_name", "encoding", "endian"),
    [
        ("ply", "ascii", "<"),
        ("ply", "binary_little_endian", "<"),
        ("ply", "binary_big_endian", ">"),
        ("pcd", "ascii", "<"),
        ("pcd", "binary", "<"),
    ],
)
def test_independent_scrambled_mixed_width_fields_survive_every_format(
    tmp_path: Path, format_name: str, encoding: str, endian: str
) -> None:
    """Generate bytes with struct rather than the writer and retain non-XYZ field order."""
    rows = [(2**32 - 1, -1e-9, 65535, 0.125, -125.75, 0xFA1020), (0, 1.25, 0, -0.5, 1e-12, 0)]
    if format_name == "ply":
        header = (
            f"ply\nformat {encoding} 1.0\nelement vertex 2\nproperty uint label\n"
            "property double x\nproperty ushort intensity\nproperty float z\n"
            "property double y\nproperty uint rgb\nend_header\n"
        )
    else:
        header = (
            "# independent fixture\nVERSION .7\nFIELDS label x intensity z y rgb\n"
            "SIZE 4 8 2 4 8 4\nTYPE U F U F F U\nCOUNT 1 1 1 1 1 1\nWIDTH 2\n"
            f"HEIGHT 1\nPOINTS 2\nDATA {encoding}\n"
        )
    body = (
        "".join(" ".join(str(value) for value in row) + "\n" for row in rows).encode()
        if encoding == "ascii"
        else b"".join(struct.pack(endian + "IdHfdI", *row) for row in rows)
    )
    path = tmp_path / "content-detection.bin"
    path.write_bytes(header.encode() + body)
    cloud = load_cloud(path)
    assert cloud.data.dtype.names == ("label", "x", "intensity", "z", "y", "rgb")
    assert cloud.data["label"][0] == 2**32 - 1
    assert cloud.data["intensity"][0] == 65535
    assert cloud.data["rgb"][0] == 0xFA1020
    path.write_bytes(dump_cloud(cloud))
    restored = load_cloud(path)
    np.testing.assert_array_equal(restored.data, cloud.data)
    assert restored.fields == cloud.fields


def test_unit_policy_and_new_probe_follow_clipped_geometry(
    make_file: FileFactory, output_dir: Path
) -> None:
    """A custom unit threshold survives transforms, while shrinking extents refreshes its result."""
    source = _cloud(make_file, [(0, 0, 0), (5, 1, 1), (15, 0, 1), (40, 1, 0)])
    checked = (
        REGISTRY["pointcloud.unit_check"]
        .run([source], output_dir, {"expected_max_extent": 20.0})
        .files[0]
    )
    assert checked.metadata["pointcloud_probe"]["unit_suspected"] is True
    clipped = (
        REGISTRY["pointcloud.clean"]
        .run([checked], output_dir, {"max_bound": [15.0, 1.0, 1.0]})
        .files[0]
    )
    assert clipped.metadata["pointcloud_probe_params"]["expected_max_extent"] == 20
    assert clipped.metadata["pointcloud_probe"]["point_count"] == 3
    assert clipped.metadata["pointcloud_probe"]["unit_suspected"] is False
    assert clipped.metadata["source_pointcloud_probe"]["unit_suspected"] is True
    assert clipped.metadata.get("pointcloud_unit_check", {}).get("suspected") is not True


def test_geometry_transform_cannot_reuse_previous_preview(
    make_file: FileFactory, output_dir: Path
) -> None:
    """A retained preview must describe the current point bytes instead of source geometry."""
    source = _cloud(make_file, [(0, 0, 0), (1, 1, 1), (100, 100, 3)])
    rendered = REGISTRY["pointcloud.preview"].run([source], output_dir, {"size": 64}).files[0]
    previous = rendered.metadata["pointcloud_preview"]
    clipped = (
        REGISTRY["pointcloud.clean"]
        .run([rendered], output_dir, {"max_bound": [2.0, 2.0, 2.0]})
        .files[0]
    )
    assert clipped.metadata.get("pointcloud_preview") != previous
    refreshed = REGISTRY["pointcloud.preview"].run([clipped], output_dir, {"size": 64}).files[0]
    assert refreshed.metadata["pointcloud_preview"]["sha256"] != previous["sha256"]
    assert refreshed.metadata["pointcloud_probe"]["point_count"] == 2


def test_invalid_point_cleanup_refreshes_scoring_without_losing_source_reason(
    make_file: FileFactory, output_dir: Path
) -> None:
    """Score cleaned finite points and retain the original NaN rate as source attribution."""
    source = _cloud(make_file, [(0, 0, 0), (0.1, 0.1, 0.1), (0.2, 0.2, 0.2), (float("nan"), 0, 0)])
    probed = REGISTRY["pointcloud.probe"].run([source], output_dir).files[0]
    original = assess_file(probed)
    cleaned = REGISTRY["pointcloud.clean"].run([probed], output_dir).files[0]
    actual = assess_file(cleaned)
    assert original.completeness == 0.75
    assert actual.completeness == 1
    assert cleaned.metadata["source_pointcloud_probe"]["invalid_ratio"] == 0.25
    assert "pointcloud_invalid_ratio" in {issue.code for issue in original.issues}
    assert "pointcloud_invalid_ratio" not in {issue.code for issue in actual.issues}


def test_statistical_outliers_are_stable_under_input_permutation_and_translation() -> None:
    """Challenge scalable Morton neighborhoods with a new anisotropic point distribution."""
    rng = np.random.default_rng(1701)
    dense = rng.normal(size=(4200, 3)) * np.array([2, 0.005, 0.005])
    sparse = rng.uniform(30, 80, size=(60, 3))
    xyz = np.vstack((dense, sparse))
    params = StatisticalParams()
    expected = outlier_mask(xyz, params)
    shuffled = rng.permutation(len(xyz))
    restored = np.empty(len(xyz), dtype=bool)
    restored[shuffled] = outlier_mask(xyz[shuffled] + [1250, -37, 4], params)
    np.testing.assert_array_equal(restored, expected)
    assert expected[-60:].all()
    # The Gaussian's own thinning tails are judged against their local neighbors, not the core.
    assert expected[:4200].mean() < 0.002


def test_batch_unit_hint_uses_geometry_and_survives_preview(
    make_file: FileFactory, output_dir: Path
) -> None:
    """A small scan a thousand times larger than its peers gets a hint, not a defect."""
    files = [_cloud(make_file, [(0, 0, 0), (extent, 0, 0)]) for extent in (0.8, 1.1, 800)]
    measured = REGISTRY["pointcloud.unit_check"].run(files, output_dir).files
    probes = [item.metadata["pointcloud_probe"] for item in measured]
    assert [probe["unit_suspected"] for probe in probes] == [False, False, False]
    assert [probe["unit_hint"] is not None for probe in probes] == [False, False, True]
    policy = measured[-1].metadata["pointcloud_probe_params"]
    assert policy["reference_extent"] == pytest.approx(0.95)
    assert measured[-1].metadata["pointcloud_unit_check"]["suggested_scale"] == 0.001
    assert assess_file(measured[-1]).consistency == 1
    rendered = REGISTRY["pointcloud.preview"].run([measured[-1]], output_dir).files[0]
    assert rendered.metadata["pointcloud_probe"]["unit_hint"] is not None
    assert rendered.metadata["pointcloud_probe_params"] == policy


def test_custom_scale_ratio_produces_matching_conversion_hint(
    make_file: FileFactory, output_dir: Path
) -> None:
    """Explicit ratio configuration cannot leave a contradictory hard-coded unit hint."""
    source = _cloud(make_file, [(0, 0, 0), (100, 0, 0)])
    measured = (
        REGISTRY["pointcloud.unit_check"]
        .run([source], output_dir, {"reference_extent": 1.0, "scale_ratio": 100.0})
        .files[0]
    )
    assert measured.metadata["pointcloud_probe"]["unit_suspected"] is False
    assert measured.metadata["pointcloud_unit_check"]["hint"] is not None
    assert measured.metadata["pointcloud_unit_check"]["suggested_scale"] == 0.01


def test_five_dimension_mapping_and_selection_cap_use_current_probe(
    make_file: FileFactory,
) -> None:
    """Keep invalid geometry, units and distribution penalties in their declared dimensions."""
    source = _cloud(make_file, [(0, 0, 0), (1, 1, 1)])
    source = source.model_copy(
        update={
            "metadata": {
                "pointcloud_probe": {
                    "point_count": 100,
                    "invalid_ratio": 0.1,
                    "outlier_ratio": 0.2,
                    "density": 2,
                    "unit_suspected": True,
                    "unit_reason": "independent_unit_suspicion",
                }
            }
        }
    )
    assessment = assess_file(source)
    assert assessment.completeness == 0.9
    assert assessment.consistency == 0.2
    assert assessment.distribution == 0.8
    assert assessment.score == 20
    quality = score_quality([source])
    assert quality.dimensions["completeness"].score == 90
    assert quality.dimensions["consistency"].score == 20
    assert quality.dimensions["distribution"].score == 80
    dataset = DatasetRow(name="independent-scoring", files=[], quality_config={})
    assert file_quality(source, dataset) == 20
