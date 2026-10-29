# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Match dates and typed numbers against their cited evidence."""

import re
import unicodedata
from datetime import date
from decimal import Decimal
from typing import NamedTuple

from pydantic import JsonValue

from datakeel.core.datasheet_models import DatasheetFact
from datakeel.datasheets.number_labels import (
    has_label,
    key_labels,
    modality_key,
    number_context,
    number_labels,
)
from datakeel.datasheets.units import (
    Reading,
    count_label,
    count_unit,
    reading_spans,
    supported,
    text_readings,
)

# Chinese dates may space their 年/月/日 markers; numeric separators stay unspaced.
_DATE = re.compile(
    r"(?<!\d)(\d{4})(?:[-/.]|[ \t]*年[ \t]*)(\d{1,2})(?:[-/.]|[ \t]*月[ \t]*)(\d{1,2})"
    r"(?:[ \t]*日)?(?!\d)"
)
_MONTHS = {
    name: number
    for number, names in enumerate(
        (
            "jan january",
            "feb february",
            "mar march",
            "apr april",
            "may",
            "jun june",
            "jul july",
            "aug august",
            "sep sept september",
            "oct october",
            "nov november",
            "dec december",
        ),
        start=1,
    )
    for name in names.split()
}
_MONTH_PATTERN = "(?:" + "|".join(sorted(_MONTHS, key=len, reverse=True)) + ")"
_NAMED_DATE = re.compile(r"\b(" + _MONTH_PATTERN + r")\.?\s+(\d{1,2}),?\s+(\d{4})\b", re.IGNORECASE)
_DAY_FIRST_DATE = re.compile(
    r"\b(\d{1,2})\s+(" + _MONTH_PATTERN + r")\.?\s+(\d{4})\b", re.IGNORECASE
)
# A clock is compared whole, like a date, as in 2026-10-27T15:55:01.562095.
_CLOCK = re.compile(r"(?<!\d)(\d{1,2}):(\d{2})(?::(\d{2})(?:\.(\d+))?)?(?!\d)")


def normalized(value: str) -> str:
    """Normalize compatibility glyphs and case without conflating separate words."""
    value = unicodedata.normalize("NFKC", value).casefold()
    return re.sub(r"(?<=\d)\s+(?:percent|per cent)\b", "%", value)


def value_strings(value: JsonValue) -> tuple[str, ...]:
    """Flatten JSON leaves and keys while retaining complete entity strings."""
    if isinstance(value, dict):
        return tuple(value) + tuple(part for item in value.values() for part in value_strings(item))
    if isinstance(value, list):
        return tuple(part for item in value for part in value_strings(item))
    if value is None:
        return ("null",)
    if isinstance(value, bool):
        return (str(value).lower(),)
    return (str(value),)


def _date(value: re.Match[str]) -> str:
    try:
        return date(*(int(part) for part in value.groups())).isoformat()
    except ValueError:
        return value.group()


def _named_date(match: re.Match[str], *, day_first: bool) -> str:
    month, day, year = match.groups()
    if day_first:
        month, day = day, month
    try:
        return date(int(year), _MONTHS[month.casefold()], int(day)).isoformat()
    except ValueError:
        return match.group()


def _clock_prefixes(match: re.Match[str]) -> tuple[str, ...]:
    # A recorded clock may be stated to the minute or second, never with other parts.
    hour, minute, second, fraction = match.groups()
    clock = f"T{int(hour)}:{int(minute)}"
    values = [clock]
    if second is not None:
        values.append(clock := f"{clock}:{int(second)}")
    if fraction is not None:
        values.append(f"{clock}.{fraction}")
    return tuple(values)


def _dates(text: str) -> set[str]:
    values = {_date(match) for match in _DATE.finditer(text)}
    values.update(_named_date(match, day_first=False) for match in _NAMED_DATE.finditer(text))
    values.update(_named_date(match, day_first=True) for match in _DAY_FIRST_DATE.finditer(text))
    values.update(value for match in _CLOCK.finditer(text) for value in _clock_prefixes(match))
    return values


def erase_dates(text: str) -> str:
    """Remove whole calendar dates before checking their component numbers or words."""
    return _DAY_FIRST_DATE.sub(" ", _NAMED_DATE.sub(" ", _DATE.sub(" ", text)))


def _loose_numbers(text: str) -> str:
    # Calendar days and clocks are checked whole above; their parts are not loose numbers.
    return _CLOCK.sub(" ", erase_dates(text))


_MEASURED = {
    "count": "count",
    "ratio": "ratio",
    "percent": "percent",
    "score": "score",
    "bytes": "bytes",
    "duration": "duration",
    "date": "date",
}


def _measured(fact: DatasheetFact) -> str | None:
    if fact.kind == "amount":
        return f"amount:{fact.unit}" if fact.unit else "amount"
    if fact.kind == "count":
        return count_unit(fact.unit or fact.field) or "count"
    return _MEASURED.get(fact.kind)


def fact_readings(fact: DatasheetFact) -> frozenset[Reading]:
    """Type every recorded number by its fact kind, or by its own words in recorded text."""
    measured = _measured(fact)
    readings: set[Reading] = set()

    def visit(value: JsonValue) -> None:
        if isinstance(value, bool) or value is None:
            return
        if isinstance(value, int | float):
            readings.add((Decimal(str(value)), measured))
        elif isinstance(value, str):
            text = normalized(value)
            for match in _DATE.finditer(text):
                readings.update((Decimal(part), "date") for part in match.groups() if part)
            for item, unit in text_readings(_loose_numbers(text)):
                readings.add((item, unit if measured is None or unit == "percent" else measured))
        elif isinstance(value, dict):
            for key, item in value.items():
                visit(key)
                visit(item)
        else:
            for item in value:
                visit(item)

    visit(fact.value)
    return frozenset(readings)


class _NumberEvidence(NamedTuple):
    labels: tuple[str, ...]
    readings: frozenset[Reading]
    keyed: bool = False
    parent_labels: tuple[str, ...] = ()
    modality: str | None = None


def _number_evidence(fact: DatasheetFact) -> tuple[_NumberEvidence, ...]:
    labels = tuple(normalized(label) for label in number_labels(fact.field))
    if isinstance(fact.value, dict) and fact.kind == "count":
        evidence: list[_NumberEvidence] = []
        for key, value in fact.value.items():
            child = fact.model_copy(update={"value": value})
            readings = fact_readings(child)
            # A modality can be stated as images or image files, always under its own key.
            if fact.field == "manifest.modalities" and (unit := count_unit(key)):
                readings |= frozenset((value, unit) for value, _unit in readings)
            evidence.append(
                _NumberEvidence(
                    tuple(normalized(label) for label in key_labels(key)),
                    readings,
                    keyed=True,
                    parent_labels=labels,
                    modality=key_labels(key)[0] if fact.field == "manifest.modalities" else None,
                )
            )
        return tuple(evidence)
    return (_NumberEvidence(labels, fact_readings(fact)),)


def _selected_evidence(
    before: str, after: str, evidence: tuple[_NumberEvidence, ...]
) -> tuple[_NumberEvidence, ...]:
    preceding = any(has_label(before, item.labels) for item in evidence)
    local = before if preceding else after
    scoped = any(has_label(local, item.parent_labels) for item in evidence)
    modality = modality_key(local, before=preceding)
    return tuple(
        item
        for item in evidence
        if has_label(local, item.labels)
        and (not scoped or has_label(local, item.parent_labels))
        and (item.modality is None or modality is None or modality == item.modality)
    )


def _record_label_reading(
    reading: Reading, after: str, selected: tuple[_NumberEvidence, ...]
) -> Reading:
    label = count_label(after.strip(" \t\n.,;:!?。'\""))
    if reading[1] == "count:unknown" and any(
        item.keyed and label in item.labels for item in selected
    ):
        # An exact recorded key can follow its value when the repeated object is omitted.
        return reading[0], None
    return reading


def _unsupported_numbers(text: str, evidence: tuple[_NumberEvidence, ...]) -> bool:
    text = _loose_numbers(text)
    spans = reading_spans(text)
    for index, (start, end, raw_reading) in enumerate(spans):
        previous = spans[index - 1][1] if index else 0
        following = spans[index + 1][0] if index + 1 < len(spans) else len(text)
        before, after = number_context(text[previous:start], text[end:following])
        selected = _selected_evidence(before, after, evidence)
        reading = _record_label_reading(raw_reading, after, selected)
        recorded = frozenset(
            value for item in evidence if not item.keyed for value in item.readings
        )
        available = frozenset(value for item in selected for value in item.readings) or recorded
        labelled = frozenset(
            (value, reading[1])
            for item in selected
            for value, unit in item.readings
            if (reading[1] is None and unit != "date")
            or (reading[1] == "count" and unit is not None and unit.startswith("count"))
        )
        if reading[1] == "count":
            available = frozenset(item for item in available if item[1] is None)
        if not supported(reading, available | labelled):
            return True
    return False


def numeric_issues(text: str, facts: tuple[DatasheetFact, ...]) -> tuple[str, ...]:
    """Require dates, and numbers under the same unit, in cited values, never in fact IDs."""
    candidates = tuple(normalized(part) for fact in facts for part in value_strings(fact.value))
    dates = {item for part in candidates for item in _dates(part)}
    dates.update(fact.recorded_at.date().isoformat() for fact in facts)
    numbers = tuple(item for fact in facts for item in _number_evidence(fact))
    issues: list[str] = []
    if _dates(normalized(text)) - dates:
        issues.append("unsupported_date")
    if _unsupported_numbers(normalized(text), numbers):
        issues.append("unsupported_number")
    return tuple(issues)
