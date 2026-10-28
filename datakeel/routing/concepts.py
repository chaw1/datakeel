# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Match declared workflow concepts with English inflections and literal token boundaries."""

import re
from functools import lru_cache
from typing import Literal

from datakeel.workflows.models import WorkflowTriggers

_IRREGULAR = {
    "do": ("did", "done", "does"),
    "get": ("got", "gotten"),
    "give": ("gave", "given"),
    "go": ("went", "gone", "goes"),
    "make": ("made",),
    "redo": ("redid", "redone", "redoes"),
    "rerun": ("reran",),
    "run": ("ran",),
    "sweep": ("swept",),
    "take": ("took", "taken"),
    "throw": ("threw", "thrown"),
}
_DOUBLING_MAX_LENGTH = 5
_DOUBLING = re.compile(r"(?:^|[^aeiou])[aeiou][^aeiouwxy]$")


def normalize(text: str) -> str:
    """Match Unicode case-insensitively with normalized whitespace."""
    return " ".join(text.casefold().split())


def position(text: str, expression: str) -> int | None:
    """Return the earliest literal match of any ``|`` alternative, respecting token edges."""
    positions: list[int] = []
    for alternative in expression.split("|"):
        term = normalize(alternative)
        prefix = r"(?<![a-z0-9_])" if term[0].isascii() and term[0].isalnum() else ""
        suffix = r"(?![a-z0-9_])" if term[-1].isascii() and term[-1].isalnum() else ""
        match = re.search(prefix + re.escape(term) + suffix, text)
        if match:
            positions.append(match.start())
    return min(positions) if positions else None


def inflected_position(text: str, expression: str) -> int | None:
    """Match alternatives plus regular and common irregular forms of their outer words."""
    forms = [form for alternative in expression.split("|") for form in _term_forms(alternative)]
    return position(text, "|".join(forms))


def concept_match(text: str, triggers: WorkflowTriggers) -> bool:
    """Require a declared entity, a declared action and any declared follow-up outcome."""
    concepts = triggers.concepts
    if concepts is None:
        return False
    required = [concepts.entities, concepts.actions]
    if concepts.outcomes:
        required.append(concepts.outcomes)
    return all(
        any(inflected_position(text, term) is not None for term in terms) for terms in required
    )


def concept_excluded(text: str, triggers: WorkflowTriggers) -> bool:
    """Return whether the request uses wording the workflow declares out of its scope."""
    concepts = triggers.concepts
    if concepts is None:
        return False
    return any(inflected_position(text, term) is not None for term in concepts.exclusions)


def concept_terms(
    triggers: WorkflowTriggers,
    *roles: Literal["entities", "actions", "outcomes", "exclusions"],
) -> list[str]:
    """List the declared phrasings of the given roles (entities and actions by default)."""
    concepts = triggers.concepts
    if concepts is None:
        return []
    selected = roles or ("entities", "actions")
    return [term for role in selected for term in getattr(concepts, role)]


def anchor_terms(triggers: WorkflowTriggers) -> list[str]:
    """Return the words that tie a clause to a workflow: its entities and legacy anchors."""
    entities = [] if triggers.concepts is None else triggers.concepts.entities
    return [*entities, *triggers.verification_keywords]


def verification_terms(triggers: WorkflowTriggers) -> list[str]:
    """Return the concept vocabulary, keeping legacy verification words for older contracts."""
    terms = [*concept_terms(triggers), *triggers.verification_keywords]
    return terms or triggers.classification_keywords


@lru_cache(maxsize=4096)
def _term_forms(term: str) -> tuple[str, ...]:
    words = normalize(term).split(" ")
    if not words[0]:
        return (term,)
    firsts = _word_forms(words[0])
    if len(words) == 1:
        return tuple(sorted(firsts))
    lasts = _word_forms(words[-1])
    middle = words[1:-1]
    return tuple(sorted(" ".join([first, *middle, last]) for first in firsts for last in lasts))


def _word_forms(word: str) -> set[str]:
    forms = {word, *_IRREGULAR.get(word, ())}
    if not (word.isascii() and word.isalpha() and len(word) > 1):
        return forms
    if word.endswith("e"):
        forms.update({word + "s", word + "d", word[:-1] + "ing"})
    elif word.endswith("y") and word[-2] not in "aeiou":
        forms.update({word[:-1] + "ies", word[:-1] + "ied", word + "ing"})
    else:
        sibilant = word.endswith(("s", "x", "z", "ch", "sh"))
        forms.update({word + ("es" if sibilant else "s"), word + "ed", word + "ing"})
        if len(word) <= _DOUBLING_MAX_LENGTH and _DOUBLING.search(word):
            forms.update({word + word[-1] + "ed", word + word[-1] + "ing"})
    return forms
