# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Sensor regressions fail when gap, outlier or declared-unit guards are removed."""

from scripts.mutation_models import Mutation

TIMESERIES_MUTATIONS = (
    Mutation(
        name="timeseries-missing-gap-guard",
        path="operators/timeseries/gaps.py",
        before="if delta > expected * params.tolerance:",
        after="if False:",
        case=(
            "tests/operators/timeseries/test_gaps.py::"
            "test_gaps_detected_per_device_with_total_missing_duration"
        ),
        runner="pytest",
    ),
    Mutation(
        name="timeseries-missing-robust-z-guard",
        path="operators/timeseries/rules.py",
        before="if score > params.robust_z_threshold:",
        after="if False:",
        case=(
            "tests/operators/timeseries/test_anomaly.py::"
            "test_zero_mad_spike_is_detected_without_marking_constant_neighbors"
        ),
        runner="pytest",
    ),
    Mutation(
        name="timeseries-missing-unit-guard",
        path="operators/timeseries/unit_check.py",
        before="if unit and _canonical(unit) != _canonical(declaration.unit):",
        after="if False:",
        case=(
            "tests/operators/timeseries/test_unit_check.py::"
            "test_unit_suffix_conflicts_and_physical_range_have_source_evidence"
        ),
        runner="pytest",
    ),
)
