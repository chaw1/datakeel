# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Check sampled measurement, its interval, unit independence and sensor policy."""

import numpy as np
import pytest

from datakeel.operators.pointcloud import probe
from datakeel.operators.pointcloud.models import ProbeParams
from datakeel.operators.pointcloud.statistics import analyse
from tests.operators.pointcloud import scans
from tests.operators.pointcloud.helpers import make_cloud


def test_stratified_sample_is_deterministic_unique_and_spatially_even() -> None:
    """Every region keeps its share of points, and the same file gives the same sample."""
    xyz = scans.vehicle_scan()
    rows = probe.stratified_sample(xyz, 4000)
    assert len(rows) == 4000
    assert np.array_equal(rows, np.unique(rows))
    np.testing.assert_array_equal(rows, probe.stratified_sample(xyz, 4000))
    for axis in range(3):
        cut = float(np.median(xyz[:, axis]))
        assert abs((xyz[rows, axis] <= cut).mean() - 0.5) < 0.03
    reordered = np.random.default_rng(3).permutation(len(xyz))
    again = reordered[probe.stratified_sample(xyz[reordered], 4000)]
    assert len(np.intersect1d(again, rows)) > 0.99 * len(rows)


def test_wilson_interval_matches_reference_values() -> None:
    """The 95% score interval stays inside [0, 1] and covers zero counts sensibly."""
    assert probe.wilson_interval(0, 0) == (0.0, 0.0)
    low, high = probe.wilson_interval(5, 100)
    assert low == pytest.approx(0.02154, abs=1e-5)
    assert high == pytest.approx(0.11175, abs=1e-5)
    low, high = probe.wilson_interval(0, 1000)
    assert low == 0
    assert high == pytest.approx(0.00383, abs=1e-5)
    assert probe.wilson_interval(1000, 1000)[1] == 1


@pytest.mark.parametrize("fraction", [0.0, 0.005, 0.02])
def test_sampled_probe_reaches_the_full_verdict(
    monkeypatch: pytest.MonkeyPatch, fraction: float
) -> None:
    """A file measured on a half sample reaches the verdict of a full measurement.

    The interval covers the sampling error of the proportion only. Thinning
    also widens surface spacing faster than the gaps between scattered
    strays, so the sampled ratio sits somewhat off the full one; a half
    sample is what a million-point file gets.
    """
    points = scans.indoor_scan()
    cloud = make_cloud(scans.scatter(points, fraction) if fraction else points)
    full = probe.inspect_cloud(cloud)
    assert not full.outlier_sampled
    assert full.outlier_ci_low == full.outlier_ratio == full.outlier_ci_high
    monkeypatch.setattr(probe, "FULL_LIMIT", full.point_count // 2)
    sampled = probe.inspect_cloud(cloud)
    assert sampled.outlier_sampled
    assert sampled.outlier_sample_count == full.point_count // 2
    assert sampled.outlier_ci_low <= sampled.outlier_ratio <= sampled.outlier_ci_high
    assert sampled.relative_spacing == pytest.approx(full.relative_spacing, rel=0.3)
    assert sampled.body_extent == pytest.approx(full.body_extent, rel=0.05)
    limit = ProbeParams().max_outlier_ratio
    assert (sampled.outlier_ci_low > limit) is (full.outlier_ratio > limit) is (fraction > 0)
    if fraction:
        assert 0.75 * full.outlier_ratio <= sampled.outlier_ratio <= 1.5 * full.outlier_ratio
    else:
        assert sampled.outlier_ci_low == 0


def test_supplied_full_analysis_gives_the_same_probe() -> None:
    """Operators that already analysed every row reuse it instead of measuring twice."""
    xyz = scans.scatter(scans.depth_scan(), 0.005)
    cloud = make_cloud(xyz)
    params = ProbeParams()
    assert probe.inspect_cloud(cloud, params, analyse(xyz, params)) == probe.inspect_cloud(
        cloud, params
    )


def test_relative_spacing_and_outliers_do_not_depend_on_the_unit() -> None:
    """The same part in millimeters and meters measures alike and is not suspected."""
    millimeters = probe.inspect_cloud(make_cloud(scans.small_part()))
    meters = probe.inspect_cloud(make_cloud(scans.small_part(millimeters=False)))
    assert millimeters.relative_spacing == pytest.approx(meters.relative_spacing, rel=1e-6)
    assert millimeters.outlier_ratio == meters.outlier_ratio
    assert millimeters.body_extent == pytest.approx(meters.body_extent * 1000, rel=1e-6)
    assert millimeters.relative_spacing < ProbeParams().spacing_limit()
    assert not millimeters.unit_suspected
    assert millimeters.unit_hint is None
    declared = probe.inspect_cloud(make_cloud(scans.small_part()), ProbeParams(sensor="object"))
    assert declared.unit_suspected
    assert declared.unit_reason == "extent_exceeds_expected_maximum_possible_millimeters"


@pytest.mark.parametrize(
    ("sensor", "limit", "penalized"),
    [("unknown", 0.01, False), ("depth_camera", 0.01, True), ("vehicle_lidar", 0.005, True)],
)
def test_sparse_policy_follows_the_declared_sensor(
    *, sensor: str, limit: float, penalized: bool
) -> None:
    """A low-resolution depth frame exceeds the spacing limit; only a declared form is judged."""
    declared = ProbeParams.model_validate({"sensor": sensor})
    coarse = probe.inspect_cloud(make_cloud(scans.depth_scan(40, 30)), declared)
    assert coarse.relative_spacing > 0.01
    assert coarse.spacing_limit == limit
    assert coarse.sparse_penalized is penalized
    assert coarse.sensor == sensor
    fine = probe.inspect_cloud(make_cloud(scans.depth_scan()), declared)
    assert fine.relative_spacing < limit / 1.5


def test_explicit_spacing_limit_is_always_penalized() -> None:
    """A user-supplied limit replaces the sensor default and is enforced without a sensor."""
    params = ProbeParams(max_relative_spacing=0.002)
    measured = probe.inspect_cloud(make_cloud(scans.depth_scan()), params)
    assert measured.spacing_limit == 0.002
    assert measured.sparse_penalized
