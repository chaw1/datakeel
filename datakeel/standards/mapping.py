# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Deterministic explainable mapping suggestions with no model or network calls."""

import re
from decimal import Decimal

from datakeel.core.standard_models import (
    ColumnProfile,
    FieldStandard,
    MappingCandidate,
    MappingSuggestion,
    StandardsContract,
    StandardValue,
    standard_value_key,
)
from datakeel.standards.names import compatible_type, name_tokens

SUGGESTION_THRESHOLD = 0.58
_NAME_THRESHOLD = 0.45
_GENERIC = frozenset({"id", "code", "name", "type", "status", "date", "time", "amount"})


def _name_score(profile: ColumnProfile, standard: FieldStandard) -> float:
    observed = name_tokens(profile.name)
    best = 0.0
    for name in (standard.code, standard.name_zh, standard.name_en, *standard.aliases):
        expected = name_tokens(name)
        if not expected or not observed:
            continue
        common = observed & expected
        if observed == expected:
            return 0.82
        if expected <= observed and expected - _GENERIC:
            extra = len(observed - expected)
            best = max(best, 0.65 * len(expected) / (len(expected) + 0.25 * extra))
        if common and (common - _GENERIC or expected <= observed):
            overlap = len(common) / max(len(observed), len(expected))
            best = max(best, 0.8 * overlap)
    return best


def _value_evidence(
    profile: ColumnProfile, standard: FieldStandard, contract: StandardsContract
) -> tuple[float, tuple[str, ...]]:
    values = [value for value in profile.values if value is not None]
    if not values:
        return 0, ()
    score = 0.0
    reasons: list[str] = []
    code_list = next(
        (item for item in contract.code_lists if item.code == standard.code_list), None
    )
    if code_list is not None:
        allowed = {standard_value_key(entry.value) for entry in code_list.entries}
        ratio = sum(standard_value_key(value) in allowed for value in values) / len(values)
        score += 0.08 * ratio
        reasons.append(f"Code-list value hit rate: {ratio:.0%}")
    if standard.pattern is not None:
        ratio = sum(
            re.fullmatch(standard.pattern, str(value)) is not None for value in values
        ) / len(values)
        score += 0.04 * ratio
        reasons.append(f"Pattern value hit rate: {ratio:.0%}")
    if standard.minimum is not None or standard.maximum is not None:
        ratio = sum(_in_range(value, standard) for value in values) / len(values)
        score += 0.04 * ratio
        reasons.append(f"Numeric range value hit rate: {ratio:.0%}")
    if standard.required:
        ratio = sum(value is not None and value != "" for value in profile.values) / len(
            profile.values
        )
        score += 0.02 * ratio
        reasons.append(f"Nonempty observed value rate: {ratio:.0%}")
    return score, tuple(reasons)


def _in_range(value: StandardValue, standard: FieldStandard) -> bool:
    if not isinstance(value, (int, float, Decimal)) or isinstance(value, bool):
        return False
    number = Decimal(str(value))
    return (
        number.is_finite()
        and (standard.minimum is None or number >= Decimal(str(standard.minimum)))
        and (standard.maximum is None or number <= Decimal(str(standard.maximum)))
    )


def _candidate(
    profile: ColumnProfile, standard: FieldStandard, contract: StandardsContract
) -> MappingCandidate | None:
    lexical = _name_score(profile, standard)
    if lexical < _NAME_THRESHOLD:
        return None
    score, value_reasons = _value_evidence(profile, standard, contract)
    score += lexical
    reasons = [f"Name tokens match {standard.name_en} ({lexical:.2f})"]
    if compatible_type(profile.data_type, standard.data_type):
        score += 0.1
        reasons.append(f"Compatible type: {profile.data_type} / {standard.data_type}")
    else:
        score -= 0.12
        reasons.append(f"Type differs: {profile.data_type} / {standard.data_type}")
    if score < SUGGESTION_THRESHOLD:
        return None
    return MappingCandidate(
        standard_code=standard.code,
        score=round(min(score, 1.0), 3),
        reasons=tuple(reasons) + value_reasons,
    )


def suggest(profile: ColumnProfile, contract: StandardsContract) -> MappingSuggestion:
    """Rank the top three active standards and abstain when name evidence is weak."""
    candidates = [
        candidate
        for standard in contract.standards
        if standard.status == "active"
        and (candidate := _candidate(profile, standard, contract)) is not None
    ]
    candidates.sort(key=lambda candidate: (-candidate.score, candidate.standard_code))
    return MappingSuggestion(column_id=profile.column_id, candidates=tuple(candidates[:3]))
