# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""An edit that names what to edit but not what to change is asked about, never planned.

"把 Mia 的技能改一下" names a person and a kind of change but no new value; a card that
changes nothing would only confuse. Each editing action lists the parameters that count as
a change; when none is given the reply asks which one, in words.
"""

import re

from datakeel.core.intent_models import Candidate, Clarification
from datakeel.intents.catalog import FIELD_KINDS, LIST_KINDS, EntityCatalog, candidates
from datakeel.intents.drafts import DraftStep
from datakeel.intents.plain_words import enum_label
from datakeel.intents.signatures import choice_values
from datakeel.intents.wording import field_label

# (action, operation or "") -> the parameters that are a change.
CHANGES: dict[tuple[str, str], tuple[str, ...]] = {
    ("manage_users", "update"): ("display_name", "status", "role_ids", "skill_ids", "team_ids"),
    ("manage_users", "update_team"): ("name", "leader_id"),
    ("manage_skills", "update"): ("name", "annotation_type", "domain", "level"),
    ("configure_project", ""): (
        "lease_minutes",
        "dispatch_strategy",
        "skill_requirement",
        "max_active_tasks",
        "clear",
    ),
}
CHOICES = 8
# A change said in other words still counts: role_id for role_ids.
ALSO = {"role_ids": ("role_id",)}


def nothing_to_edit(step: DraftStep) -> tuple[str, ...]:
    """The parameters that could change, when the step gives none of them; else empty."""
    operation = step.params.get("operation")
    changes = CHANGES.get((step.action, operation if isinstance(operation, str) else ""), ())
    given = {
        name
        for name in changes
        for key in (name, *ALSO.get(name, ()))
        if step.params.get(key) not in (None, "")
    }
    return () if given or not changes else changes


def _core(label: str) -> str:
    """A label without its unit: "lease (minutes)" is said as "lease"."""
    return re.sub(r"\s*\([^)]*\)", "", label).strip().casefold()


def _named(step: DraftStep, changes: tuple[str, ...], text: str) -> str | None:
    """The one changeable item the sentence names ("派单方式改一下"), if exactly one."""
    words = text.casefold()
    named = {
        name
        for name in changes
        if name in step.params
        or any(_core(field_label(name, language)) in words for language in ("zh", "en"))
    }
    return named.pop() if len(named) == 1 else None


def value_question(
    step: DraftStep, slot: tuple[str, tuple[str, ...]], language: str, catalog: EntityCatalog
) -> Clarification:
    """The item is named: ask only for its new value, offering the allowed ones."""
    field, changes = slot
    label = field_label(field, language)
    kind = FIELD_KINDS.get(field) or LIST_KINDS.get(field)
    choices = (
        candidates(catalog.of(kind))[:CHOICES]
        if kind
        else [
            Candidate(id=value, label=enum_label(value, language), kind="value")
            for value in choice_values(step.action, field)
        ]
    )
    separator = "、" if language == "zh" else ", "
    shown = separator.join(choice.label for choice in choices)
    others = separator.join(field_label(name, language) for name in changes if name != field)
    if language == "zh":
        offered = f"可以改成: {shown}" if choices else f"直接说新的{label}; 也可以改: {others}"
        question = f"{label}要改成什么? {offered}。"
    elif choices:
        question = f"What should {label} become? You can change it to: {shown}."
    else:
        question = f"What should {label} become? Say the new value; you can also change: {others}."
    return Clarification(question=question, action=step.action, fields=[field], candidates=choices)


def edit_question(
    step: DraftStep,
    changes: tuple[str, ...],
    language: str,
    said: tuple[str, EntityCatalog] = ("", EntityCatalog()),
) -> Clarification:
    """Ask which of the changeable things should change; a named one is asked its value."""
    named = _named(step, changes, said[0])
    if named is not None:
        return value_question(step, (named, changes), language, said[1])
    separator = "、" if language == "zh" else ", "
    labels = separator.join(field_label(name, language) for name in changes)
    question = (
        f"要改哪一项, 改成什么? 可以改: {labels}。"
        if language == "zh"
        else f"What should change, and to what? You can change: {labels}."
    )
    return Clarification(question=question, action=step.action, fields=list(changes))
