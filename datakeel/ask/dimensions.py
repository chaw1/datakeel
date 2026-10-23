# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Resolve dimension values only inside the selected metric's declared slicing scope."""

import re

from datakeel.ask.matching import occurrences
from datakeel.ask.models import DimensionParse
from datakeel.core.ask_models import MatchEvidence
from datakeel.core.metric_models import (
    DimensionDefinition,
    DimensionSlice,
    MetricCard,
    SemanticLayer,
)


def parse_dimensions(question: str, card: MetricCard, layer: SemanticLayer) -> DimensionParse:
    """Collect supported dimension slices and refuse conflicting values."""
    matches: list[MatchEvidence] = []
    slices: list[DimensionSlice] = []
    groups: list[str] = []
    issues: list[str] = []
    for dimension in layer.dimensions:
        if dimension.id not in card.definition.dimensions:
            continue
        values = _value_matches(question, dimension)
        matches.extend(values)
        selected = sorted({item.value for item in values if item.value is not None})
        if len(selected) > 1:
            issues.append(f"Multiple values for dimension {dimension.id} require clarification")
        elif selected:
            slices.append(DimensionSlice(dimension_id=dimension.id, value=selected[0]))
        for item in _dimension_matches(question, dimension, layer):
            matches.append(item)
            if question[max(0, item.start - 1) : item.start] in {"各", "按"}:
                groups.append(dimension.id)
    if _unknown_region(question, matches):
        issues.append("Region value is not registered for this metric")
    return DimensionParse(
        slices=tuple(slices),
        group_by=tuple(sorted(set(groups))),
        matches=tuple(sorted(matches, key=lambda item: (item.start, item.source))),
        issues=tuple(issues),
    )


def _value_matches(question: str, dimension: DimensionDefinition) -> list[MatchEvidence]:
    return [
        MatchEvidence(
            start=hit.start(),
            end=hit.end(),
            text=hit.group(),
            source=f"dimension:{dimension.id}.values[{index}]",
            match_kind="dimension_value",
            dimension_id=dimension.id,
            value=value,
        )
        for index, value in enumerate(dimension.values)
        for hit in occurrences(question, value)
    ]


def _dimension_matches(
    question: str, dimension: DimensionDefinition, layer: SemanticLayer
) -> list[MatchEvidence]:
    matches: list[MatchEvidence] = []
    for label in [dimension.name, *dimension.synonyms]:
        term_id = next(
            (
                f"term/{term.term}"
                for term in layer.terms
                if term.means.kind == "dimension"
                and term.means.id == dimension.id
                and label in [term.term, *term.synonyms]
            ),
            None,
        )
        matches.extend(
            MatchEvidence(
                start=hit.start(),
                end=hit.end(),
                text=hit.group(),
                source=f"dimension:{dimension.id}.name",
                match_kind="exact" if label == dimension.name else "synonym",
                dimension_id=dimension.id,
                term_id=term_id,
            )
            for hit in occurrences(question, label)
        )
    for term in layer.terms:
        if term.means.kind != "dimension" or term.means.id != dimension.id:
            continue
        for label in [term.term, *term.synonyms]:
            matches.extend(
                MatchEvidence(
                    start=hit.start(),
                    end=hit.end(),
                    text=hit.group(),
                    source=f"term:{term.term}",
                    match_kind="exact" if label == term.term else "synonym",
                    dimension_id=dimension.id,
                    term_id=f"term/{term.term}",
                )
                for hit in occurrences(question, label)
            )
    return matches


def _unknown_region(question: str, matches: list[MatchEvidence]) -> bool:
    remainder = list(question)
    for item in matches:
        remainder[item.start : item.end] = " " * (item.end - item.start)
    return re.search(r"[\u4e00-\u9fff]{2,4}区", "".join(remainder)) is not None
