# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Pure timestamp and measurement parsing checks do not use ambient locale or services."""

import pytest

from datakeel.core.errors import ValidationError
from datakeel.operators.timeseries.parsing import finite_number, measured_number, parse_time


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("1970-01-01T00:00:00.001Z", 1),
        ("1970-01-01T01:00:00+01:00", 0),
        ("1767225600", 1767225600000),
        ("1767225600000", 1767225600000),
        ("1.5", 1500),
        ("-1.5", -1500),
    ],
)
def test_timestamp_formats_have_deterministic_utc_milliseconds(value: str, expected: int) -> None:
    """ISO offsets and automatic modern epochs represent deterministic UTC instants."""
    assert parse_time(value).milliseconds == expected


def test_explicit_epoch_unit_disambiguates_historic_small_milliseconds() -> None:
    """A caller can remove magnitude ambiguity for historic millisecond data."""
    assert parse_time("1500", numeric_unit="ms").milliseconds == 1500


@pytest.mark.parametrize("value", ["", "not a time", "NaN", "1e1000"])
def test_invalid_timestamp_fails_with_domain_error(value: str) -> None:
    """Malformed and overflowing values never produce a fake instant."""
    with pytest.raises(ValidationError):
        parse_time(value)


@pytest.mark.parametrize("value", ["2026-03-08T02:30:00", "2026-11-01T01:30:00"])
def test_dst_fold_and_gap_require_explicit_offset(value: str) -> None:
    """Missing or ambiguous local times cannot be guessed during daylight-saving transitions."""
    with pytest.raises(ValidationError, match="Ambiguous or nonexistent"):
        parse_time(value, "America/New_York")


@pytest.mark.parametrize("value", ["NaN", "inf", "-inf", "", "4 C"])
def test_nonfinite_or_suffixed_cells_are_not_plain_numeric(value: str) -> None:
    """Statistics cannot accidentally ingest infinities or strip unrequested units."""
    assert finite_number(value) is None


def test_measurement_parser_preserves_explicit_suffix() -> None:
    """An explicit suffix remains available for declaration checking."""
    assert measured_number(" 1.2e2 m³/h ") == (120.0, "m³/h")
    assert measured_number("not numeric") is None
    assert measured_number("1e1000 C") is None
