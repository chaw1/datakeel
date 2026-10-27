# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Explicit UTC calendar intervals for supported Chinese and English time expressions."""

import re
from datetime import UTC, date, datetime, timedelta

from datakeel.ask import time_vocabulary as vocab
from datakeel.ask.models import TimeAtom, TimeParse
from datakeel.ask.time_atoms import FUTURE_ISSUE, extract_atoms, shift_months
from datakeel.core.ask_models import MatchEvidence
from datakeel.core.metric_models import TimeRange

AS_OF_START = date(1, 1, 1)
INVALID_ISSUE = "Invalid time expression"
_YEAR_CONTEXT = "year_context"
_RANGE_JOIN_AND = re.compile(r"^\s*and\s*(?:the\s+)?$", re.IGNORECASE)


def parse_time(question: str, reference_instant: datetime) -> TimeParse:
    """Resolve recognized expressions and refuse conflicting, invalid or future requests."""
    reference = reference_instant.astimezone(UTC).date()
    expressions = time_expressions(question, reference)
    intervals: list[TimeRange] = []
    issues: list[str] = []
    for atom in expressions:
        if atom.kind == _YEAR_CONTEXT:
            continue
        issue = atom.issue
        if issue is None and atom.interval_start is not None and atom.interval_start >= reference:
            issue = FUTURE_ISSUE
        if issue is not None:
            issues.append(f"{issue}: {question[atom.start : atom.end].strip()}")
        elif atom.interval_start is not None and atom.interval_end is not None:
            intervals.append(TimeRange(start=atom.interval_start, end=atom.interval_end))
    if len(set(intervals)) > 1:
        issues.append("Multiple distinct time intervals require clarification")
    resolved = bool(intervals) and not issues
    as_of = any(atom.kind.startswith("as_of") for atom in expressions)
    return TimeParse(
        time_range=intervals[0] if resolved else None,
        basis=("as_of" if as_of else "period") if resolved else None,
        matches=tuple(
            MatchEvidence(
                start=atom.start,
                end=atom.end,
                text=question[atom.start : atom.end],
                source=f"time:{atom.kind}",
                match_kind="time",
            )
            for atom in expressions
        ),
        issues=tuple(issues),
    )


def time_spans(question: str, reference: date) -> tuple[tuple[int, int], ...]:
    """Return every consumed time span, including attached prepositions and anchors."""
    return tuple((atom.start, atom.end) for atom in time_expressions(question, reference))


def time_expressions(question: str, reference: date) -> list[TimeAtom]:
    """Combine atoms into ranges and anchored boundaries, then resolve every interval."""
    atoms = _year_context(_joined_ranges(question, extract_atoms(question, reference), reference))
    resolved = [
        atom
        if atom.kind in {_YEAR_CONTEXT, "range"}
        else _anchored(question, _resolve(atom, reference), reference)
        for atom in atoms
    ]
    return [_attached(question, atom) for atom in resolved]


def _joined_ranges(question: str, atoms: list[TimeAtom], reference: date) -> list[TimeAtom]:
    joined: list[TimeAtom] = []
    index = 0
    while index < len(atoms):
        first = atoms[index]
        second = atoms[index + 1] if index + 1 < len(atoms) else None
        opener = vocab.RANGE_OPEN.search(question[: first.start])
        between = question[first.end : second.start] if second else ""
        paired = second is not None and vocab.RANGE_JOIN.fullmatch(between) is not None
        if paired and _RANGE_JOIN_AND.fullmatch(between):
            paired = opener is not None and "between" in opener.group().casefold()
        if second is None or not paired:
            joined.append(first)
            index += 1
            continue
        start = opener.start() if opener else first.start
        joined.append(_range(first, second, start, reference))
        index += 2
    return joined


def _range(first: TimeAtom, second: TimeAtom, start: int, reference: date) -> TimeAtom:
    if first.year is None and second.year is not None:
        first = first.model_copy(update={"year": second.year})
    if second.year is None and first.year is not None:
        second = second.model_copy(update={"year": first.year})
    begin, finish = _resolve(first, reference), _resolve(second, reference)
    lower, upper = begin.interval_start, finish.interval_end
    issue = begin.issue or finish.issue
    if issue is None and (lower is None or upper is None or upper <= lower):
        issue = INVALID_ISSUE
    return TimeAtom(
        start=start,
        end=second.end,
        kind="range",
        interval_start=lower,
        interval_end=upper,
        issue=issue,
    )


def _year_context(atoms: list[TimeAtom]) -> list[TimeAtom]:
    years = [atom for atom in atoms if atom.kind == "year"]
    missing = [atom for atom in atoms if atom.year is None and atom.months]
    if len(years) != 1 or not missing:
        return atoms
    context = years[0]
    return [
        atom.model_copy(update={"kind": _YEAR_CONTEXT})
        if atom is context
        else atom.model_copy(update={"year": context.year})
        if atom in missing
        else atom
        for atom in atoms
    ]


def _bounds(atom: TimeAtom, year: int) -> tuple[date, date]:
    if atom.day is not None:
        start = date(year, atom.month, atom.day)
        return start, start + timedelta(days=1)
    start = date(year, atom.month, 1)
    return start, shift_months(start, atom.months)


def _resolve(atom: TimeAtom, reference: date) -> TimeAtom:
    if not atom.months or atom.interval_start is not None or atom.issue is not None:
        return atom
    year = reference.year if atom.year is None else atom.year
    try:
        start, end = _bounds(atom, year)
    except ValueError:
        return atom.model_copy(update={"issue": INVALID_ISSUE})
    if atom.year is None and start > reference:
        return atom.model_copy(update={"issue": FUTURE_ISSUE})
    return atom.model_copy(update={"year": year, "interval_start": start, "interval_end": end})


def _anchored(question: str, atom: TimeAtom, reference: date) -> TimeAtom:
    before, after = question[: atom.start], question[atom.end :]
    prefix, suffix = vocab.AS_OF_PREFIX.search(before), vocab.AS_OF_SUFFIX.match(after)
    if prefix or suffix:
        return atom.model_copy(
            update={
                "kind": f"as_of_{atom.kind}",
                "start": prefix.start() if prefix else atom.start,
                "end": atom.end + (suffix.end() if suffix else 0),
                "interval_start": AS_OF_START,
            }
        )
    prefix, suffix = vocab.SINCE_PREFIX.search(before), vocab.SINCE_SUFFIX.match(after)
    if not (prefix or suffix):
        return atom
    since = atom.model_copy(
        update={
            "kind": f"since_{atom.kind}",
            "start": prefix.start() if prefix else atom.start,
            "end": atom.end + (suffix.end() if suffix else 0),
            "interval_end": reference,
        }
    )
    if atom.interval_start is not None and atom.interval_start >= reference:
        return since.model_copy(update={"issue": atom.issue or FUTURE_ISSUE})
    return since


def _attached(question: str, atom: TimeAtom) -> TimeAtom:
    lead = vocab.LEAD.search(question[: atom.start])
    possessive = vocab.POSSESSIVE.match(question[atom.end :])
    return atom.model_copy(
        update={
            "start": lead.start() if lead else atom.start,
            "end": atom.end + (possessive.end() if possessive else 0),
        }
    )
