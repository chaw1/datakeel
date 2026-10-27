# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Resolve dimension values only inside the selected metric's declared slicing scope."""

import re

from datakeel.ask import dimension_cues as cues
from datakeel.ask.matching import occurrences
from datakeel.ask.models import DimensionParse
from datakeel.core.ask_models import MatchEvidence
from datakeel.core.metric_models import (
    DimensionDefinition,
    DimensionSlice,
    MetricCard,
    SemanticLayer,
)


def parse_dimensions(
    question: str,
    card: MetricCard,
    layer: SemanticLayer,
    occupied: tuple[tuple[int, int], ...] = (),
) -> DimensionParse:
    """Collect supported slices and groupings, refusing every role that cannot be applied."""
    allowed = set(card.definition.dimensions)
    mentions = [
        item
        for item in dimension_mentions(question, layer)
        if all(item.end <= start or item.start >= end for start, end in occupied)
    ]
    hits = _selected(mentions, allowed)
    issues = [
        f"Dimension is not available for this metric: {question[item.start : item.end]}"
        for item in hits
        if item.dimension_id not in allowed
    ]
    usable = [item for item in hits if item.dimension_id in allowed]
    values = [item for item in usable if item.value is not None]
    names = [item for item in usable if item.value is None]
    known = [*occupied, *((item.start, item.end) for item in mentions)]
    known.extend(_metric_words(question, card))
    slices, consumed, value_issues = _value_roles(question, values, known)
    groups, name_spans, name_issues = _name_roles(question, names, values)
    if _unknown_region(question, usable):
        issues.append("Region value is not registered for this metric")
    return DimensionParse(
        slices=tuple(slices),
        group_by=tuple(sorted(set(groups))),
        matches=tuple(sorted(usable, key=lambda item: (item.start, item.source))),
        issues=(*issues, *value_issues, *name_issues),
        consumed=tuple(
            sorted(
                [
                    *consumed,
                    *name_spans,
                    *((item.start, item.end) for item in hits if item.dimension_id not in allowed),
                ]
            )
        ),
    )


def dimension_mentions(question: str, layer: SemanticLayer) -> list[MatchEvidence]:
    """Find every registered dimension name, synonym, glossary term, value and value alias."""
    found: list[MatchEvidence] = []
    for dimension in layer.dimensions:
        found.extend(_value_matches(question, dimension))
        found.extend(_dimension_matches(question, dimension, layer))
    return found


def _selected(found: list[MatchEvidence], allowed: set[str]) -> list[MatchEvidence]:
    """Keep the longest spans; an identical span prefers the metric's own dimension."""
    ordered = sorted(
        found,
        key=lambda item: (item.start - item.end, item.dimension_id not in allowed, item.start),
    )
    selected: list[MatchEvidence] = []
    for item in ordered:
        if all(item.end <= other.start or item.start >= other.end for other in selected):
            selected.append(item)
    return sorted(selected, key=lambda item: item.start)


def _value_roles(
    question: str, values: list[MatchEvidence], known: list[tuple[int, int]]
) -> tuple[list[DimensionSlice], list[tuple[int, int]], list[str]]:
    consumed: list[tuple[int, int]] = []
    issues: list[str] = []
    chosen: dict[str, set[str]] = {}
    for item in values:
        before, after = question[: item.start], question[item.end :]
        text = question[item.start : item.end]
        if cues.NEGATION_BEFORE.search(before) or cues.NEGATION_AFTER.match(after):
            issues.append(f"Excluding a dimension value is not supported: {text}")
            continue
        if cues.VALUE_GROUP_BEFORE.search(before):
            issues.append(f"Grouping by an individual value is not supported: {text}")
            continue
        if _compound(question, item, known):
            issues.append(f"Dimension value is part of an unrecognized phrase: {text}")
            continue
        lead = cues.FILTER_BEFORE.search(before)
        consumed.append((lead.start() if lead else item.start, item.end))
        chosen.setdefault(item.dimension_id or "", set()).add(item.value or "")
    slices: list[DimensionSlice] = []
    for dimension_id, selected in sorted(chosen.items()):
        if len(selected) > 1:
            issues.append(f"Multiple values for dimension {dimension_id} require clarification")
        else:
            slices.append(DimensionSlice(dimension_id=dimension_id, value=next(iter(selected))))
    return slices, consumed, issues


def _name_roles(
    question: str, names: list[MatchEvidence], values: list[MatchEvidence]
) -> tuple[list[str], list[tuple[int, int]], list[str]]:
    groups: list[str] = []
    consumed: list[tuple[int, int]] = []
    issues: list[str] = []
    for item in names:
        before, after = question[: item.start], question[item.end :]
        cue, suffix = cues.GROUP_BEFORE.search(before), cues.GROUP_AFTER.match(after)
        if cue or suffix:
            groups.append(item.dimension_id or "")
            start = cue.start() if cue else item.start
            consumed.append((start, item.end + (suffix.end() if suffix else 0)))
        elif _names_value(question, item, values):
            lead = cues.FILTER_BEFORE.search(before)
            consumed.append((lead.start() if lead else item.start, item.end))
        else:
            text = question[item.start : item.end]
            issues.append(f"Dimension needs a value or a grouping: {text}")
    return groups, consumed, issues


def _metric_words(question: str, card: MetricCard) -> list[tuple[int, int]]:
    """Locate words of the metric's own English names, which may follow a value alias."""
    definition = card.definition
    names = [definition.english_name or "", definition.id.replace("_", " "), *definition.synonyms]
    words = {word for name in names if name.isascii() for word in name.casefold().split()}
    words |= {word + "s" for word in words}
    return [
        (hit.start(), hit.end())
        for hit in re.finditer(r"[A-Za-z]+", question)
        if hit.group().casefold() in words
    ]


def _compound(question: str, item: MatchEvidence, known: list[tuple[int, int]]) -> bool:
    """Detect an English alias that only starts a longer noun phrase, such as a job title."""
    after = question[item.end :]
    if not question[item.start : item.end].isascii() or cues.VALUE_FOLLOWER.match(after):
        return False
    following = item.end + len(after) - len(after.lstrip())
    return not any(start <= following < end for start, end in known)


def _names_value(question: str, name: MatchEvidence, values: list[MatchEvidence]) -> bool:
    return any(
        value.dimension_id == name.dimension_id
        and cues.NAME_VALUE_GAP.fullmatch(
            question[value.end : name.start]
            if value.end <= name.start
            else question[name.end : value.start]
        )
        is not None
        for value in values
    )


def _value_matches(question: str, dimension: DimensionDefinition) -> list[MatchEvidence]:
    labels = [
        (value, f"dimension:{dimension.id}.values[{index}]", value)
        for index, value in enumerate(dimension.values)
    ]
    labels.extend(
        (alias, f"dimension:{dimension.id}.value_synonyms[{value}][{index}]", value)
        for value, aliases in dimension.value_synonyms.items()
        for index, alias in enumerate(aliases)
    )
    return [
        MatchEvidence(
            start=hit.start(),
            end=hit.end(),
            text=hit.group(),
            source=source,
            match_kind="dimension_value",
            dimension_id=dimension.id,
            value=value,
        )
        for label, source, value in labels
        for hit in occurrences(question, label)
    ]


def _dimension_matches(
    question: str, dimension: DimensionDefinition, layer: SemanticLayer
) -> list[MatchEvidence]:
    terms = [
        term
        for term in layer.terms
        if term.means.kind == "dimension" and term.means.id == dimension.id
    ]
    labels: list[tuple[str, str, str | None]] = []
    for label in [dimension.name, dimension.english_name or "", *dimension.synonyms]:
        term_id = next(
            (f"term/{term.term}" for term in terms if label in [term.term, *term.synonyms]), None
        )
        labels.append((label, f"dimension:{dimension.id}.name", term_id))
    labels.extend(
        (label, f"term:{term.term}", f"term/{term.term}")
        for term in terms
        for label in [term.term, *term.synonyms]
    )
    return [
        MatchEvidence(
            start=hit.start(),
            end=hit.end(),
            text=hit.group(),
            source=source,
            match_kind="exact" if label in {dimension.name, dimension.english_name} else "synonym",
            dimension_id=dimension.id,
            term_id=term_id,
        )
        for label, source, term_id in labels
        for hit in occurrences(question, label)
    ]


def _unknown_region(question: str, matches: list[MatchEvidence]) -> bool:
    remainder = list(question)
    for item in matches:
        remainder[item.start : item.end] = " " * (item.end - item.start)
    return re.search(r"[一-鿿]{2,4}区", "".join(remainder)) is not None
