# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Check deterministic planted-pair generation and truthful process measurements."""

from pathlib import Path

import pytest

from scripts.near_duplicate_benchmark import run_case
from scripts.near_duplicate_benchmark_data import Measurement, generate_workload


def test_generated_workload_has_independent_boundary_crossing_gold() -> None:
    """Every planted distance is known, and half the pairs cross a four-bit prefix."""
    workload = generate_workload(1000)
    assert workload == generate_workload(1000)
    assert workload != generate_workload(1000, seed=123)
    assert len(workload.planted) == 10
    assert all(
        (workload.hashes[left] ^ workload.hashes[right]).bit_count() == distance
        for left, right, distance in workload.planted
    )
    assert (
        sum(
            workload.hashes[left] >> 60 != workload.hashes[right] >> 60
            for left, right, _distance in workload.planted
        )
        == 5
    )


def test_workload_rejects_nonpositive_size() -> None:
    """Invalid input cannot create an empty benchmark with misleading perfect recall."""
    with pytest.raises(ValueError, match="positive"):
        generate_workload(0)


@pytest.mark.parametrize(("mode", "recall"), [("prefix", 0.5), ("exact", 1.0)])
def test_python_measurement_scores_only_planted_pairs(
    mode: str, recall: float, tmp_path: Path
) -> None:
    """A fresh process reports measured time/RSS and exposes the expected prefix misses."""
    request = Measurement.model_validate(
        {
            "size": 1000,
            "implementation": "python",
            "mode": mode,
            "status": "completed",
            "elapsed_seconds": 0,
            "wall_seconds": 0,
            "peak_rss_bytes": 0,
            "timeout_seconds": 30,
            "seed": 20261027,
            "planted_pairs": 10,
        }
    )
    result = run_case(request, tmp_path)
    assert result.status == "completed"
    assert result.recall == recall
    assert result.elapsed_seconds > 0
    assert result.peak_rss_bytes > 0
    assert result.workload_digest == generate_workload(1000).digest


def test_timeout_records_observed_wall_time_and_peak_rss(tmp_path: Path) -> None:
    """A killed child is an explicit timeout, with no invented recall or pair count."""
    request = Measurement(
        size=1000,
        implementation="python",
        mode="prefix",
        status="completed",
        elapsed_seconds=0,
        wall_seconds=0,
        peak_rss_bytes=0,
        timeout_seconds=0.001,
        seed=20261027,
        planted_pairs=10,
    )
    result = run_case(request, tmp_path)
    assert result.status == "timeout"
    assert result.wall_seconds >= request.timeout_seconds
    assert result.recall is None
    assert result.returned_pairs is None
