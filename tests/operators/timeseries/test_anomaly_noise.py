# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Independent seeded noise, trend and fault-boundary regressions."""

from collections import Counter
from collections.abc import Callable
from pathlib import Path

import numpy as np
import pytest

from datakeel.core.models import FileItem
from datakeel.operators.timeseries.anomaly import OPERATOR
from datakeel.operators.timeseries.models import AnomalySummary

SEEDS = (20261027, 20261028, 20261029)
SPIKES = {157, 1223, 2709, 4001, 5663}


@pytest.mark.parametrize("seed", SEEDS)
@pytest.mark.parametrize("slope", [0.0, 0.02])
def test_stationary_and_linear_noisy_signals_limit_false_alarms_and_recall_spikes(
    table_file: Callable[..., FileItem], tmp_path: Path, seed: int, slope: float
) -> None:
    """A trend's constant slope must not inflate the centered difference-noise estimate."""
    random = np.random.default_rng(seed)
    rows = [
        (
            str(index * 1000),
            "a",
            str(42 + slope * index + random.normal(0, 1) + (20 if index in SPIKES else 0)),
        )
        for index in range(6000)
    ]
    file = table_file(rows, ("timestamp", "device_id", "temperature"))
    output = OPERATOR.run([file], tmp_path / "out").files[0]
    summary = AnomalySummary.model_validate(output.metadata["timeseries"]["anomaly"])
    outliers = [issue for issue in summary.issues if issue.rule == "robust_z"]
    detected = {row - 2 for issue in outliers for row in issue.rows}
    assert detected >= SPIKES
    assert len(detected - SPIKES) <= 2
    assert all("max(local_mad, noise_mad)" in issue.detail for issue in outliers)


@pytest.mark.parametrize("seed", SEEDS)
def test_stuck_recovery_has_no_secondary_alarm_and_adjacent_spike_remains_detectable(
    table_file: Callable[..., FileItem], tmp_path: Path, seed: int
) -> None:
    """Exclude a proved fault from references while still inspecting neighboring normal targets."""
    random = np.random.default_rng(seed)
    stuck = set(range(700, 760))
    spike = 762
    rows = [
        (
            str(index * 1000),
            "a",
            str(42 if index in stuck else 42 + random.normal(0, 1) + (20 if index == spike else 0)),
        )
        for index in range(1500)
    ]
    file = table_file(rows, ("timestamp", "device_id", "temperature"))
    output = OPERATOR.run([file], tmp_path / "out").files[0]
    summary = AnomalySummary.model_validate(output.metadata["timeseries"]["anomaly"])
    outliers = [issue for issue in summary.issues if issue.rule == "robust_z"]
    assert {row - 2 for issue in outliers for row in issue.rows} == {spike}
    constant = [issue for issue in summary.issues if issue.rule == "stuck_value"]
    assert len(constant) == 1
    assert constant[0].rows == tuple(index + 2 for index in sorted(stuck))
    assert "excluded_stuck=0" not in outliers[0].detail
    assert 3 <= outliers[0].window <= 31


def test_noise_floor_can_be_disabled_explicitly(
    table_file: Callable[..., FileItem], tmp_path: Path
) -> None:
    """The switch preserves a way to request uncalibrated small-window local MAD behavior."""
    random = np.random.default_rng(SEEDS[0])
    file = table_file(
        [(str(index * 1000), "a", str(25 + random.normal(0, 1))) for index in range(6000)],
        ("timestamp", "device_id", "temperature"),
    )
    counts = {}
    for enabled in (False, True):
        output = OPERATOR.run(
            [file], tmp_path / str(enabled), {"window": 11, "noise_floor": enabled}
        ).files[0]
        summary = AnomalySummary.model_validate(output.metadata["timeseries"]["anomaly"])
        counts[enabled] = sum(issue.rule == "robust_z" for issue in summary.issues)
    assert counts[False] > 2
    assert counts[True] <= 2


def test_insufficient_clean_reference_skips_robust_claim_but_preserves_other_rules(
    table_file: Callable[..., FileItem], tmp_path: Path
) -> None:
    """Masking a stuck baseline cannot silently disable declared jumps or physical bounds."""
    values = [20] * 5 + [100] + [20] * 5
    file = table_file(
        [(str(index * 1000), "a", str(value)) for index, value in enumerate(values)],
        ("timestamp", "device_id", "temperature"),
    )
    output = OPERATOR.run(
        [file],
        tmp_path / "out",
        {
            "jump_threshold": 30,
            "ranges": [{"column": "temperature", "maximum": 80}],
        },
    ).files[0]
    summary = AnomalySummary.model_validate(output.metadata["timeseries"]["anomaly"])
    assert Counter(issue.rule for issue in summary.issues) == {
        "stuck_value": 2,
        "jump": 2,
        "out_of_range": 1,
    }
