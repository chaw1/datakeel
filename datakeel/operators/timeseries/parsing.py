# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Parse timestamps and finite numeric cells without locale-dependent guesses."""

import math
import re
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from datakeel.core.errors import ValidationError
from datakeel.core.models import Record

NUMERIC = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$")
MEASURED = re.compile(r"^\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)\s*(.*?)\s*$")
MILLISECOND_BOUNDARY = Decimal(100000000000)


class ParsedTime(Record):
    """Describe an observed timestamp and the basis for its UTC interpretation."""

    milliseconds: int
    format: str
    timezone: str
    inferred: bool = False


def finite_number(value: str) -> float | None:
    """Return a finite numeric cell, leaving empty and suffixed cells unparsed."""
    try:
        number = float(value)
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def measured_number(value: str) -> tuple[float, str] | None:
    """Separate a finite number from its explicit optional unit suffix."""
    match = MEASURED.fullmatch(value)
    if match is None:
        return None
    number = finite_number(match[1])
    return None if number is None else (number, match[2])


def _naive_time(parsed: datetime, timezone: str) -> datetime:
    try:
        zone = ZoneInfo(timezone)
    except ZoneInfoNotFoundError as exc:
        msg = f"Unknown naive_timezone: {timezone}"
        raise ValidationError(msg) from exc
    first = parsed.replace(tzinfo=zone, fold=0)
    second = parsed.replace(tzinfo=zone, fold=1)
    if first.utcoffset() != second.utcoffset():
        msg = "Ambiguous or nonexistent local time; supply an explicit UTC offset"
        raise ValidationError(msg)
    if first.astimezone(UTC).astimezone(zone).replace(tzinfo=None) != parsed:
        msg = "Nonexistent local time; supply an explicit UTC offset"
        raise ValidationError(msg)
    return first


def parse_time(
    value: str, naive_timezone: str = "UTC", numeric_unit: Literal["auto", "s", "ms"] = "auto"
) -> ParsedTime:
    """Accept ISO 8601 or epoch seconds/milliseconds and return UTC milliseconds.

    Auto epochs use absolute magnitude 100 billion as the declared separator.
    Historic small millisecond values require numeric_unit='ms'. ISO naive times
    use the explicitly configured timezone; DST folds and gaps are rejected.
    """
    stripped = value.strip()
    if NUMERIC.fullmatch(stripped):
        return _epoch_time(stripped, numeric_unit)
    try:
        parsed = datetime.fromisoformat(stripped)
    except ValueError as exc:
        msg = "Timestamp must be ISO 8601 or a finite numeric epoch"
        raise ValidationError(msg) from exc
    naive = parsed.tzinfo is None
    aware = _naive_time(parsed, naive_timezone) if naive else parsed
    offset = aware.strftime("%z")
    return ParsedTime(
        milliseconds=int(aware.timestamp() * 1000),
        format="iso8601_naive" if naive else "iso8601_offset",
        timezone=f"assumed:{naive_timezone}" if naive else offset,
        inferred=naive,
    )


def _epoch_time(value: str, unit: Literal["auto", "s", "ms"]) -> ParsedTime:
    try:
        number = Decimal(value)
        selected = unit
        if selected == "auto":
            selected = "ms" if abs(number) >= MILLISECOND_BOUNDARY else "s"
        milliseconds = int(number if selected == "ms" else number * 1000)
        datetime.fromtimestamp(milliseconds / 1000, UTC)
    except (InvalidOperation, ValueError, OverflowError, OSError) as exc:
        msg = "Numeric timestamp is outside the supported datetime range"
        raise ValidationError(msg) from exc
    return ParsedTime(
        milliseconds=milliseconds,
        format=f"epoch_{selected}",
        timezone="UTC",
        inferred=unit == "auto",
    )
