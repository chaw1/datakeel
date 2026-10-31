# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""The last check on every word the planner sends to a person: no internal names.

Answers, questions, choices, card lines and notes must not show parameter keys, ``$ref``
references, snake_case names, action ids, identities or untranslated choices (``team`` or
``rework`` inside Chinese). The sources already speak plainly; this guard catches what
slips through. A known internal name is put back into words; anything still internal is
replaced by a generic sentence and logged, so the person never reads it and the source can
be fixed.
"""

import logging
import re
from collections.abc import Iterable

from pydantic import JsonValue

from datakeel.actions.registry import POLICIES
from datakeel.core.intent_models import (
    ActionChain,
    Candidate,
    ChainStep,
    Clarification,
    IntentResult,
    StepDetail,
)
from datakeel.intents.catalog import EntityCatalog
from datakeel.intents.field_names import ENUM_LABELS, MORE_LABELS
from datakeel.intents.wording import FIELD_LABELS, action_title
from datakeel.ontology.functions import PARAMETER_MODELS

logger = logging.getLogger(__name__)
UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.IGNORECASE)
REFERENCE = re.compile(r"\{?\s*\"?\$[A-Za-z_]+\"?(?::\s*\"?[\w.]*\"?)?\s*\}?")
# snake_case words; a file name such as red_light.jpg is not one.
SNAKE = re.compile(r"(?<![\w/$.-])[a-z]+(?:_[a-z]+)+(?![\w/-]|\.\w)")
WORD = re.compile(r"(?<![A-Za-z_])[a-z]+(?![A-Za-z_])")
# Choices that mean nothing left in English inside a Chinese sentence.
ZH_CHOICES = frozenset(
    {
        "personal",
        "group",
        "team",
        "claim",
        "assign",
        "skill",
        "annotation",
        "review",
        "count",
        "directory",
        "metadata",
        "approve",
        "rework",
        "pending",
        "submitted",
        "approved",
        "finalized",
    }
)
_FALLBACK = {
    "text": (
        "这一步我没法用白话说清楚, 所以没有展示细节。请换个说法再试。",
        "I could not put this into plain words, so no details are shown. Please rephrase.",
    ),
    "answer": (
        "查到了结果, 但有些内容没法直接念给你, 请到对应页面查看。",
        "I found the answer, but parts of it cannot be shown as words; please open its page.",
    ),
    "value": ("(已设置)", "(set)"),
}


def _internal_names() -> dict[str, tuple[str, str]]:
    names: dict[str, tuple[str, str]] = {**MORE_LABELS, **FIELD_LABELS}
    names.update({key: value for key, value in ENUM_LABELS.items() if "_" in key})
    return names


def allowed_words(catalog: EntityCatalog, *texts: str, labels: Iterable[str] = ()) -> set[str]:
    """Names people gave (objects, people, labels) and their own words may be repeated."""
    found = {name for entry in catalog.entries for name in (entry.label, *entry.names)}
    found.update(labels)
    found.update(word for text in texts for word in re.findall(r"[A-Za-z][\w.-]*", text))
    return {name for name in found if len(name) > 1 and not UUID.fullmatch(name)}


def leaks(text: str, language: str, allowed: set[str]) -> list[str]:
    """Internal names left in ``text`` once the allowed names are taken out."""
    rest = text
    for name in sorted(allowed, key=len, reverse=True):
        rest = rest.replace(name, " ")
    found = UUID.findall(rest) + [item.strip() for item in REFERENCE.findall(rest)]
    found += SNAKE.findall(rest)
    if language == "zh":
        found += [word for word in WORD.findall(rest) if word in ZH_CHOICES]
    return found


def _repaired(text: str, language: str, catalog: EntityCatalog) -> str:
    """Put known internal names back into words."""
    names = _internal_names()
    actions = set(POLICIES) | set(PARAMETER_MODELS)

    def snake(match: re.Match[str]) -> str:
        name = match.group(0)
        if name in actions:
            return action_title(name, language)
        if name in names:
            zh, en = names[name]
            return zh if language == "zh" else en
        return name

    def identity(match: re.Match[str]) -> str:
        entry = next((item for item in catalog.entries if item.id == match.group(0)), None)
        return entry.label if entry is not None else ""

    text = UUID.sub(identity, REFERENCE.sub("", text))
    text = SNAKE.sub(snake, text)
    if language == "zh":
        text = WORD.sub(
            lambda match: (
                ENUM_LABELS[match.group(0)][0] if match.group(0) in ZH_CHOICES else match.group(0)
            ),
            text,
        )
    return text


def public(
    text: str, language: str, catalog: EntityCatalog, allowed: set[str], role: str = "text"
) -> str:
    """``text`` without internal names: repaired when possible, else a generic sentence."""
    found = leaks(text, language, allowed)
    if not found:
        return text
    repaired = _repaired(text, language, catalog)
    if not leaks(repaired, language, allowed):
        logger.warning("Outgoing text named internals %s; put into words", sorted(set(found)))
        return repaired
    logger.warning("Outgoing text named internals %s; replaced", sorted(set(found)))
    zh, en = _FALLBACK.get(role, _FALLBACK["text"])
    return zh if language == "zh" else en


def public_details(
    details: list[StepDetail], language: str, catalog: EntityCatalog, allowed: set[str]
) -> list[StepDetail]:
    """Card lines in words: labels and values both pass the check."""
    return [
        detail.model_copy(
            update={
                "label": public(detail.label, language, catalog, allowed),
                "value": public(detail.value, language, catalog, allowed, "value"),
            }
        )
        for detail in details
    ]


def public_notes(
    notes: list[str], language: str, catalog: EntityCatalog, allowed: set[str]
) -> list[str]:
    """Notes that still name internals after repair are dropped, never shown."""
    kept = [public(note, language, catalog, allowed, "note") for note in notes]
    zh, en = _FALLBACK["text"]
    return [note for note in kept if note not in {zh, en}]


def _clarification(
    item: Clarification, language: str, catalog: EntityCatalog, allowed: set[str]
) -> Clarification:
    labels = [
        Candidate(
            id=choice.id,
            label=public(choice.label, language, catalog, allowed, "value"),
            kind=choice.kind,
        )
        for choice in item.candidates
    ]
    question = public(item.question, language, catalog, allowed)
    return item.model_copy(update={"question": question, "candidates": labels})


def _chain(
    chain: ActionChain, language: str, catalog: EntityCatalog, allowed: set[str]
) -> ActionChain:
    steps: list[ChainStep] = [
        step.model_copy(
            update={"details": public_details(step.details, language, catalog, allowed)}
        )
        for step in chain.steps
    ]
    notes = public_notes(chain.notes, language, catalog, allowed)
    return chain.model_copy(update={"steps": steps, "notes": notes})


def public_result(result: IntentResult, language: str, catalog: EntityCatalog) -> IntentResult:
    """Every word of one planner result, checked before it leaves."""
    labels = [
        name
        for step in (result.chain.steps if result.chain else [])
        for name in label_names(step.params)
    ]
    allowed = allowed_words(catalog, result.request, labels=labels)
    role = "answer" if result.kind == "answer" else "text"
    update: dict[str, object] = {"text": public(result.text, language, catalog, allowed, role)}
    if result.clarification is not None:
        update["clarification"] = _clarification(result.clarification, language, catalog, allowed)
    if result.chain is not None:
        update["chain"] = _chain(result.chain, language, catalog, allowed)
    return result.model_copy(update=update)


def label_names(params: dict[str, JsonValue]) -> list[str]:
    """Label names a step writes: new names the person may read back on the card."""
    values = [params.get("labels"), params.get("add_labels")]
    items = [item for value in values if isinstance(value, list) for item in value]
    return [
        str(item["name"])
        for item in items
        if isinstance(item, dict) and isinstance(item.get("name"), str)
    ]
