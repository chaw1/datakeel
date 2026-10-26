# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Score weighted business-token evidence without letting generic or system fields through."""

import re
from functools import lru_cache

from datakeel.core.models import BoundaryModel
from datakeel.core.standard_models import BusinessSynonyms, FieldStandard, StandardsContract
from datakeel.standards.lexical import TokenMatch, match_token
from datakeel.standards.names import name_tokens

_GENERIC = frozenset(
    {
        "id",
        "code",
        "name",
        "type",
        "flag",
        "ts",
        "time",
        "hash",
        "json",
        "ip",
        "version",
        "key",
        "uuid",
        "guid",
        "record",
        "no",
        "number",
        "identifier",
        "value",
    }
)
_SYSTEM = frozenset(
    {
        "etl",
        "hash",
        "checksum",
        "digest",
        "tenant",
        "version",
        "latitude",
        "longitude",
        "lat",
        "lon",
        "lng",
        "delete",
        "deleted",
        "deletion",
        "debug",
        "vector",
        "embedding",
        "nonce",
        "json",
        "metadata",
        "blob",
        "ip",
        "trace",
        "traceparent",
        "cache",
        "distance",
        "del",
        "dlt",
        "removed",
        "rmv",
        "tnt",
        "ver",
        "vers",
        "revision",
        "geo",
        "gps",
        "coordinate",
        "coordinates",
        "ipaddr",
        "ipaddress",
        "ipv",
        "sensitive",
    }
)
_TECHNICAL_CLOCK = frozenset(
    {
        "create",
        "created",
        "update",
        "updated",
        "load",
        "loaded",
        "extract",
        "ingest",
        "ingestion",
        "sync",
        "refresh",
        "process",
    }
)
_SYSTEM_WORDS = ("version", "revision", "tenant", "deleted", "removed", "latitude", "longitude")
_COMPLETE_SKELETON_WEIGHT = 0.85
_CONTEXTUAL = frozenset({"amount", "date", "status", "time"})


@lru_cache(maxsize=4096)
def _system_variant(token: str) -> bool:
    if re.fullmatch(r"(?:row|record|sys|system|db)(?:version|revision|hash|checksum)", token):
        return True
    return any(
        match is not None
        and (
            match.rule == "morphology"
            or (match.rule == "consonant" and match.weight >= _COMPLETE_SKELETON_WEIGHT)
        )
        for word in _SYSTEM_WORDS
        for match in (match_token(token, word),)
    )


class NameEvidence(BoundaryModel):
    """Keep the lexical score and the exact rules that explain it together."""

    score: float = 0
    reasons: tuple[str, ...] = ()


def business_tokens(name: str) -> frozenset[str]:
    """Return usable name tokens, abstaining on infrastructure and bare generic fields."""
    tokens = name_tokens(name, expand_aliases=False)
    if tokens & _SYSTEM or any(_system_variant(token) for token in tokens) or not tokens - _GENERIC:
        return frozenset()
    if tokens & _TECHNICAL_CLOCK and tokens & {"date", "time", "timestamp", "ts", "at"}:
        return frozenset()
    return tokens


@lru_cache(maxsize=2048)
def _synonyms(
    tokens: frozenset[str], groups: tuple[BusinessSynonyms, ...]
) -> tuple[frozenset[str], tuple[str, ...]]:
    pending = tokens
    replacements: frozenset[str] = frozenset()
    reasons: list[str] = []
    for alternative, canonical_name, term in _synonym_terms(groups):
        matches = _matches(pending, alternative)
        if len(matches) != len(alternative):
            continue
        canonical = name_tokens(canonical_name, expand_aliases=False)
        if alternative == canonical:
            continue
        consumed = frozenset(item.observed for item in matches)
        pending -= consumed
        replacements |= canonical
        reasons.append(f"Synonym: '{' '.join(sorted(consumed))}' means '{canonical_name}' ({term})")
        reasons.extend(
            f"{item.rule.capitalize()}: '{item.observed}' matches synonym '{item.expected}'"
            for item in matches
            if item.rule != "exact"
        )
    return pending | replacements, tuple(reasons)


@lru_cache(maxsize=32)
def _synonym_terms(
    groups: tuple[BusinessSynonyms, ...],
) -> tuple[tuple[frozenset[str], str, str], ...]:
    terms = [
        (tokens, group.canonical, term)
        for group in groups
        for term in group.alternatives
        if (tokens := name_tokens(term, expand_aliases=False)) and tokens - _GENERIC
    ]
    return tuple(sorted(terms, key=lambda item: (-len(item[0]), -len(item[2]), item[2])))


@lru_cache(maxsize=8192)
def _matches(observed: frozenset[str], expected: frozenset[str]) -> tuple[TokenMatch, ...]:
    pairs = [
        match
        for left in sorted(observed)
        for right in sorted(expected)
        if (match := match_token(left, right)) is not None
        and (left == right or (left not in _GENERIC and right not in _GENERIC))
    ]
    pairs.sort(key=lambda item: (-item.weight, item.observed, item.expected))
    used_left: set[str] = set()
    used_right: set[str] = set()
    chosen: list[TokenMatch] = []
    for match in pairs:
        if match.observed not in used_left and match.expected not in used_right:
            chosen.append(match)
            used_left.add(match.observed)
            used_right.add(match.expected)
    return tuple(chosen)


@lru_cache(maxsize=8192)
def _score(observed: frozenset[str], expected: frozenset[str]) -> NameEvidence:
    matches = _matches(observed, expected)
    business_hit = any(item.expected not in _GENERIC | _CONTEXTUAL for item in matches)
    complete_context = observed == expected and bool(expected - _GENERIC)
    if not business_hit and not complete_context:
        return NameEvidence()
    total = sum(item.weight for item in matches)
    score = 0.82 * total / max(len(observed), len(expected))
    if len(matches) == len(expected) and len(observed) > len(expected):
        score = max(score, 0.65 * total / (len(expected) + 0.25 * (len(observed) - len(expected))))
    reasons = tuple(
        f"{item.rule.capitalize()}: '{item.observed}' matches '{item.expected}'"
        for item in matches
        if item.rule != "exact"
    )
    return NameEvidence(score=score, reasons=reasons)


def name_evidence(name: str, standard: FieldStandard, contract: StandardsContract) -> NameEvidence:
    """Match bilingual names and aliases with discounted lexical and contractual rules."""
    observed = business_tokens(name)
    if not observed:
        return NameEvidence()
    expanded, synonym_reasons = _synonyms(observed, contract.synonyms)
    best = NameEvidence()
    for label in (standard.code, standard.name_zh, standard.name_en, *standard.aliases):
        expected = name_tokens(label, expand_aliases=False)
        if not expected:
            continue
        canonical, expected_reasons = _synonyms(expected, contract.synonyms)
        direct = _score(observed, expected)
        if direct.score > best.score:
            best = direct
        known_observed, known_expected = name_tokens(name), name_tokens(label)
        if known_observed != observed or known_expected != expected:
            known = _score(known_observed, known_expected)
            if known.score * 0.8 > best.score:
                best = NameEvidence(
                    score=known.score * 0.8,
                    reasons=(f"Common abbreviation or synonym: '{name}' matches '{label}'",),
                )
        if synonym_reasons or expected_reasons:
            evidence = _score(expanded, canonical)
            if evidence.score * 0.86 > best.score:
                best = NameEvidence(
                    score=evidence.score * 0.86,
                    reasons=synonym_reasons + expected_reasons + evidence.reasons,
                )
    return best
