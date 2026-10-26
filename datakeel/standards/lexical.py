# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Compare English word forms and abbreviations without a business vocabulary."""

import re

from datakeel.core.models import BoundaryModel

_VOWELS = frozenset("aeiou")
_IRREGULAR_ROOTS = {"paid": "pay"}
_MIN_PREFIX_LENGTH = 3
_MIN_ROOT_LENGTH = 3
_MIN_SUFFIXED_LENGTH = 4
_MIN_CONSONANT_LENGTH = 2
_MIN_SUBSEQUENCE_RETENTION = 0.6


class TokenMatch(BoundaryModel):
    """Describe a lexical match without making a business mapping decision."""

    weight: float
    rule: str
    observed: str
    expected: str


def _undouble(word: str) -> str:
    if len(word) > _MIN_CONSONANT_LENGTH and word[-1] == word[-2] and word[-1] not in _VOWELS:
        return word[:-1]
    return word


def _plural_forms(word: str) -> set[str]:
    forms = {word}
    if word.endswith("ies") and len(word) > _MIN_SUFFIXED_LENGTH:
        forms.add(word[:-3] + "y")
    if word.endswith("es") and len(word) > _MIN_SUFFIXED_LENGTH:
        forms.add(word[:-2])
    if (
        word.endswith("s")
        and not word.endswith(("ss", "us", "is"))
        and len(word) > _MIN_ROOT_LENGTH
    ):
        forms.add(word[:-1])
    return forms


def _derived_forms(word: str) -> set[str]:
    forms = {word, _IRREGULAR_ROOTS.get(word, word)}
    suffixes = (("ing", 5), ("ed", 4), ("ment", 6), ("ation", 7), ("ion", 6), ("al", 5))
    for suffix, minimum in suffixes:
        if suffix == "ion" and not word.endswith("tion"):
            continue
        if len(word) > minimum and word.endswith(suffix):
            root = word[: -len(suffix)]
            if suffix == "ation":
                forms.add(root + "e")
                if root != _undouble(root):
                    forms.add(_undouble(root))
            else:
                forms.update((root, _undouble(root), root + "e"))
    return forms


def _root_forms(word: str) -> frozenset[str]:
    return frozenset(root for form in _plural_forms(word) for root in _derived_forms(form))


def _american_spelling(word: str) -> str:
    normalized = re.sub(r"our(?=$|s$|ed$|ing$|able$)", "or", word)
    normalized = re.sub(r"is(e|es|ed|ing|ation|ations)$", r"iz\1", normalized)
    normalized = re.sub(r"ogue(?=$|s$)", "og", normalized)
    if len(normalized) > _MIN_ROOT_LENGTH and normalized.endswith("re"):
        normalized = normalized[:-2] + "er"
    return normalized


def _spelled_forms(forms: frozenset[str]) -> frozenset[str]:
    return frozenset(_american_spelling(form) for form in forms)


def _prefix_weight(observed: str, expected: str) -> float:
    if (
        len(observed) < _MIN_PREFIX_LENGTH
        or len(observed) >= len(expected)
        or not expected.startswith(observed)
    ):
        return 0.0
    return min(0.9, 0.65 + 0.25 * len(observed) / len(expected))


def _consonant_forms(word: str) -> frozenset[str]:
    skeleton = "".join(letter for letter in word if letter not in _VOWELS)
    initial = word[:1] if word[:1] in _VOWELS else ""
    forms = (skeleton, initial + skeleton)
    return frozenset((*forms, *(re.sub(r"(.)\1+", r"\1", form) for form in forms)))


def _is_subsequence(short: str, long: str) -> bool:
    remaining = iter(long)
    return all(any(letter == candidate for candidate in remaining) for letter in short)


def _skeleton_weight(observed: str, skeleton: str) -> float:
    if observed == skeleton:
        return 0.85
    if len(observed) < _MIN_PREFIX_LENGTH or not skeleton or observed[0] != skeleton[0]:
        return 0.0
    retention = len(observed) / len(skeleton)
    has_ending = observed[-1] == skeleton[-1] or skeleton.startswith(observed)
    if retention < _MIN_SUBSEQUENCE_RETENTION or not has_ending:
        return 0.0
    if _is_subsequence(observed, skeleton):
        return min(0.85, 0.7 + 0.15 * retention)
    return 0.0


def _consonant_weight(observed: str, expected: str) -> float:
    if len(observed) < _MIN_CONSONANT_LENGTH or any(letter in _VOWELS for letter in observed[1:]):
        return 0.0
    observed_forms = (observed, re.sub(r"(.)\1+", r"\1", observed))
    return max(
        _skeleton_weight(short, skeleton)
        for short in observed_forms
        for skeleton in _consonant_forms(expected)
    )


def match_token(observed: str, expected: str) -> TokenMatch | None:
    """Match exact words, inflections, spelling variants or shortened English tokens.

    Abbreviations are directional: the observed token abbreviates the expected word.
    Generic field vocabulary and business synonyms are handled by the caller.
    """
    left, right = observed.casefold(), expected.casefold()
    if not left or not right:
        return None
    rule, weight = "exact", 1.0
    if left != right:
        if not (left.isascii() and right.isascii() and left.isalpha() and right.isalpha()):
            return None
        left_roots, right_roots = _root_forms(left), _root_forms(right)
        if left_roots & right_roots:
            rule, weight = "morphology", 0.94
        elif _spelled_forms(left_roots) & _spelled_forms(right_roots):
            rule, weight = "spelling", 0.94
        elif prefix_weight := _prefix_weight(left, right):
            rule, weight = "prefix", prefix_weight
        elif consonant_weight := _consonant_weight(left, right):
            rule, weight = "consonant", consonant_weight
        else:
            return None
    return TokenMatch(weight=weight, rule=rule, observed=observed, expected=expected)
