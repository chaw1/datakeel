# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Test general type signals independently of the demonstration dataset."""

import pytest

from datakeel.operators.table.inference import amount_value, infer_type, numeric_value, pii_kinds
from datakeel.operators.table.models import ColumnType
from datakeel.operators.table.params import ProfileParams


@pytest.mark.parametrize(
    ("name", "values", "expected"),
    [
        ("missing", (), "empty"),
        ("sensor_id", ("00001", "00002"), "identifier"),
        ("enabled", ("true", "FALSE"), "boolean"),
        ("count", ("0", "-2", "+3"), "integer"),
        ("reading", ("1.5", "2e3"), "number"),
        ("price", ("1,200.20", "50.25"), "amount"),
        ("payment", ("$1,200.20", "$50.25"), "amount"),
        ("date", ("2026-10-01", "2026/10/02"), "date"),
        ("event_at", ("2026-10-01T00:00:00Z", "2026-10-02T08:00:00+08:00"), "datetime"),
        ("state", ("open",) * 20 + ("closed",) * 20, "enum"),
        ("note", ("red", "blue"), "string"),
        ("reading", ("1", "broken"), "string"),
        ("reading", ("inf", "-inf"), "string"),
        ("date", ("2026-02-30", "not-a-date"), "string"),
        ("time", ("invalid T date", "still not date"), "string"),
    ],
)
def test_infer_type_follows_observed_values(
    name: str, values: tuple[str, ...], expected: ColumnType
) -> None:
    """Only consistent values are promoted to a specialized inferred type."""
    assert infer_type(name, values, ProfileParams()) == expected


@pytest.mark.parametrize("value", ["inf", "-inf", "nan", "1e999", "word"])
def test_nonfinite_numeric_values_are_excluded(value: str) -> None:
    """Statistics cannot publish infinity or NaN as a measured value."""
    assert numeric_value(value) is None


@pytest.mark.parametrize("value", ["1,23", "$word", "1 200", ""])
def test_ambiguous_amounts_are_not_coerced(value: str) -> None:
    """Locale ambiguity is not silently converted into another monetary amount."""
    assert amount_value(value) is None


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("event_at", "2026-10-01T00:00:00Z"),
        ("timestamp", "1790812800000"),
        ("epoch_seconds", "1790812800"),
        ("record_id", "12345678901"),
        ("date", "2026-10-01"),
        ("counter", "12345678901234567890"),
    ],
)
def test_ids_dates_and_epochs_do_not_become_phone_findings(name: str, value: str) -> None:
    """Known data shapes are excluded despite superficially phone-like digits."""
    assert pii_kinds(name, (value,)) == ()


@pytest.mark.parametrize("value", ["+1 (415) 555-0132", "415-555-0132", "13800138000"])
def test_shared_phone_patterns_recognize_contacts(value: str) -> None:
    """The table detector reuses the text redactor's contact recognition rules."""
    assert pii_kinds("phone", (value,)) == ("phone",)
