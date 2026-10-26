# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Verify numeric moments, bounded category ordering and contact suppression."""

import json
import math

import pytest

from datakeel.operators.table.models import DistributionSummary, ValueCount
from datakeel.operators.table.statistics import distribution


def test_numeric_summary_matches_population_statistics() -> None:
    """Quantiles and standard deviation use a documented population convention."""
    summary = distribution(("1", "2", "3", "4"), "integer", (), 5)
    assert summary.numeric is not None
    assert summary.numeric.minimum == 1
    assert summary.numeric.maximum == 4
    assert summary.numeric.mean == 2.5
    assert summary.numeric.median == 2.5
    assert summary.numeric.standard_deviation == pytest.approx(math.sqrt(1.25))
    assert summary.numeric.first_quartile == 1.75
    assert summary.numeric.third_quartile == 3.25


def test_category_top_values_have_stable_tie_order_and_bound() -> None:
    """Category order uses descending count then lexical value for reproducibility."""
    summary = distribution(("z", "b", "z", "a", "a", "c"), "enum", (), 2)
    assert summary.top_values == (ValueCount(value="a", count=2), ValueCount(value="z", count=2))
    assert summary.minimum_length == summary.maximum_length == 1


def test_pii_distribution_withholds_values_and_derived_numeric_statistics() -> None:
    """Publishing a numeric minimum could otherwise copy an entire phone number."""
    summary = distribution(("13800138000", "13800138001"), "integer", ("phone",), 5)
    assert summary == DistributionSummary(top_values=(ValueCount(value="[REDACTED]", count=2),))
    assert "13800138000" not in summary.model_dump_json()


def test_extreme_finite_values_do_not_overflow_statistics() -> None:
    """Scaling prevents spurious NaN/Infinity from intermediate additions."""
    summary = distribution(("-1e308", "1e308"), "number", (), 5)
    encoded = summary.model_dump_json()
    assert "Infinity" not in encoded
    assert "NaN" not in encoded
    assert summary.numeric is not None
    assert summary.numeric.mean == 0
    assert summary.numeric.standard_deviation == 1e308
    assert json.loads(encoded)["numeric"]["median"] == 0


def test_empty_and_inconsistent_numeric_distributions_do_not_invent_statistics() -> None:
    """Unavailable measurements remain explicit nulls."""
    assert distribution((), "empty", (), 5) == DistributionSummary()
    assert distribution(("1", "invalid"), "number", (), 5).numeric is None


def test_amount_distribution_normalizes_currency_and_thousands() -> None:
    """Currency symbols do not suppress arithmetic for valid amount columns."""
    summary = distribution(("$1,200.00", "$2,400.00"), "amount", (), 5)
    assert summary.numeric is not None
    assert summary.numeric.mean == 1800
