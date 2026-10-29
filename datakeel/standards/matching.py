# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Score weighted business-token evidence without letting generic or system fields through."""

import re
from collections.abc import Iterator
from functools import lru_cache
from typing import NamedTuple

from datakeel.core.models import BoundaryModel
from datakeel.core.standard_models import BusinessSynonyms, FieldStandard, StandardsContract
from datakeel.standards.lexical import COMPLETE_RULES, TokenMatch, complete_forms, match_token
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
        "modify",
        "modified",
        "modification",
        "changed",
        "edited",
        "amended",
        "insert",
        "inserted",
    }
)
_SYSTEM_WORDS = ("version", "revision", "tenant", "deleted", "removed", "latitude", "longitude")
_COMPLETE_SKELETON_WEIGHT = 0.85
_CONTEXTUAL = frozenset({"amount", "cycle", "date", "status", "time"})
# Audit columns pair a record-maintenance verb with when (at, on, last) or who (by) changed it.
_AUDIT_COMPANIONS = frozenset({"date", "time", "timestamp", "ts", "at", "on", "by", "last"})
_KNOWN_DISCOUNT = 0.8
_SYNONYM_DISCOUNT = 0.86


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


class _Lock(NamedTuple):
    """Tokens restricted to complete matches, except abbreviating words of their own meaning."""

    tokens: frozenset[str]
    kin: frozenset[tuple[str, str]] = frozenset()


class ColumnTerms(BoundaryModel):
    """Resolve one column name against a whole contract once, before scoring each standard.

    ``complete`` holds tokens that are whole contract words (exactly, inflected or respelled);
    they keep that meaning and are never reinterpreted as abbreviations of another word.
    ``kin`` pairs such a token with words of its own synonym group, which it may still abbreviate.
    """

    name: str
    observed: frozenset[str] = frozenset()
    known: frozenset[str] = frozenset()
    complete: frozenset[str] = frozenset()
    kin: frozenset[tuple[str, str]] = frozenset()
    expanded: frozenset[str] = frozenset()
    synonym_reasons: tuple[str, ...] = ()
    synonym_weight: float = 1.0


def business_tokens(name: str) -> frozenset[str]:
    """Return usable name tokens, abstaining on infrastructure and bare generic fields."""
    tokens = name_tokens(name, expand_aliases=False)
    if tokens & _SYSTEM or any(_system_variant(token) for token in tokens) or not tokens - _GENERIC:
        return frozenset()
    if tokens & _TECHNICAL_CLOCK and tokens & _AUDIT_COMPANIONS:
        return frozenset()
    return tokens


def _labels(standard: FieldStandard) -> tuple[str, ...]:
    return (standard.code, standard.name_zh, standard.name_en, *standard.aliases)


@lru_cache(maxsize=16)
def _vocabulary(
    standards: tuple[FieldStandard, ...], groups: tuple[BusinessSynonyms, ...]
) -> frozenset[str]:
    texts = [label for standard in standards for label in _labels(standard)]
    texts.extend(term for group in groups for term in (group.canonical, *group.alternatives))
    return frozenset(
        form
        for text in texts
        for token in name_tokens(text, expand_aliases=False)
        for form in complete_forms(token)
    )


def column_terms(name: str, contract: StandardsContract) -> ColumnTerms:
    """Lock complete contract words, then expand whole synonyms before abbreviated ones."""
    observed = business_tokens(name)
    if not observed:
        return ColumnTerms(name=name)
    known = name_tokens(name)
    vocabulary = _vocabulary(contract.standards, contract.synonyms)
    complete = frozenset(token for token in observed | known if complete_forms(token) & vocabulary)
    kin = _kin(complete, contract.synonyms)
    expanded, reasons, weight = _synonyms(observed, contract.synonyms, _Lock(complete, kin))
    return ColumnTerms(
        name=name,
        observed=observed,
        known=known,
        complete=complete,
        kin=kin,
        expanded=expanded,
        synonym_reasons=reasons,
        synonym_weight=weight,
    )


def _kin(
    complete: frozenset[str], groups: tuple[BusinessSynonyms, ...]
) -> frozenset[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    for group in groups:
        words = frozenset(
            word
            for term in (group.canonical, *group.alternatives)
            for word in name_tokens(term, expand_aliases=False)
        )
        forms = frozenset(form for word in words for form in complete_forms(word))
        pairs.update(
            (token, word) for token in complete if complete_forms(token) & forms for word in words
        )
    return frozenset(pairs)


_SynonymHit = tuple[tuple[TokenMatch, ...], str, str]


def _synonym_hits(
    pending: frozenset[str], groups: tuple[BusinessSynonyms, ...], lock: _Lock
) -> list[_SynonymHit]:
    hits: list[_SynonymHit] = []
    for alternative, canonical_name, term in _synonym_terms(groups):
        matches = _matches(pending, alternative, lock)
        canonical = name_tokens(canonical_name, expand_aliases=False)
        if len(matches) == len(alternative) and alternative != canonical:
            hits.append((matches, canonical_name, term))
    # Longest phrases first; among equally long phrases the closest word wins (stable sort).
    hits.sort(key=lambda hit: (-len(hit[0]), -min(item.weight for item in hit[0])))
    return hits


@lru_cache(maxsize=2048)
def _synonyms(
    tokens: frozenset[str], groups: tuple[BusinessSynonyms, ...], lock: _Lock
) -> tuple[frozenset[str], tuple[str, ...], float]:
    """Consume each token once, preferring longer phrases and then the closest synonym.

    Locked tokens are whole contract words, so they only take complete synonym matches.
    """
    pending = tokens
    replacements: frozenset[str] = frozenset()
    reasons: list[str] = []
    weight = 1.0
    for matches, canonical_name, term in _synonym_hits(tokens, groups, lock):
        consumed = frozenset(item.observed for item in matches)
        if not consumed <= pending:
            continue
        pending -= consumed
        replacements |= name_tokens(canonical_name, expand_aliases=False)
        weight = min(weight, *(item.weight for item in matches))
        reasons.append(f"Synonym: '{' '.join(sorted(consumed))}' means '{canonical_name}' ({term})")
        reasons.extend(
            f"{item.rule.capitalize()}: '{item.observed}' matches synonym '{item.expected}'"
            for item in matches
            if item.rule != "exact"
        )
    return pending | replacements, tuple(reasons), weight


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
def _matches(
    observed: frozenset[str], expected: frozenset[str], lock: _Lock
) -> tuple[TokenMatch, ...]:
    """Pair tokens one to one; locked tokens accept only complete (non-abbreviated) matches."""
    pairs = [
        match
        for left in sorted(observed)
        for right in sorted(expected)
        if (match := match_token(left, right)) is not None
        and (left == right or (left not in _GENERIC and right not in _GENERIC))
        and (match.rule in COMPLETE_RULES or left not in lock.tokens or (left, right) in lock.kin)
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
def _score(observed: frozenset[str], expected: frozenset[str], lock: _Lock) -> NameEvidence:
    observed_context, expected_context = observed & _CONTEXTUAL, expected & _CONTEXTUAL
    if observed_context and expected_context and observed_context.isdisjoint(expected_context):
        return NameEvidence()
    matches = _matches(observed, expected, lock)
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


def _label_evidence(
    terms: ColumnTerms, label: str, expected: frozenset[str], groups: tuple[BusinessSynonyms, ...]
) -> Iterator[NameEvidence]:
    lock = _Lock(terms.complete, terms.kin)
    yield _score(terms.observed, expected, lock)
    known_expected = name_tokens(label)
    if terms.known != terms.observed or known_expected != expected:
        known = _score(terms.known, known_expected, lock)
        yield NameEvidence(
            score=known.score * _KNOWN_DISCOUNT,
            reasons=(f"Common abbreviation or synonym: '{terms.name}' matches '{label}'",),
        )
    canonical, expected_reasons, expected_weight = _synonyms(expected, groups, _Lock(expected))
    if terms.synonym_reasons or expected_reasons:
        replaced = _Lock(terms.complete | (terms.expanded - terms.observed), terms.kin)
        evidence = _score(terms.expanded, canonical, replaced)
        weight = _SYNONYM_DISCOUNT * terms.synonym_weight * expected_weight
        yield NameEvidence(
            score=evidence.score * weight,
            reasons=terms.synonym_reasons + expected_reasons + evidence.reasons,
        )


def name_evidence(
    terms: ColumnTerms, standard: FieldStandard, contract: StandardsContract
) -> NameEvidence:
    """Match bilingual names and aliases with discounted lexical and contractual rules."""
    best = NameEvidence()
    if not terms.observed:
        return best
    for label in _labels(standard):
        expected = name_tokens(label, expand_aliases=False)
        if not expected:
            continue
        for evidence in _label_evidence(terms, label, expected, contract.synonyms):
            if evidence.score > best.score:
                best = evidence
    return best
