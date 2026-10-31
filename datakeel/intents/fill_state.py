# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""What every step is filled from (page, previous turn, speaker) and how a value is asked."""

import re

from pydantic import Field, JsonValue

from datakeel.core.intent_models import Candidate, Clarification, PageContext
from datakeel.core.models import BoundaryModel
from datakeel.intents.catalog import FIELD_KINDS, LIST_KINDS, EntityCatalog
from datakeel.intents.drafts import DraftStep
from datakeel.intents.wording import field_label


class FillState(BoundaryModel):
    """Values available to every step: page context and the previous turn's objects."""

    context: PageContext = Field(default_factory=PageContext)
    focus: dict[str, str] = Field(default_factory=dict[str, str])
    actor: str = "local"
    language: str = "zh"
    text: str = ""
    # task id -> stage of the hold an earlier step of the same plan takes back
    freed: dict[str, str] = Field(default_factory=dict[str, str])
    # task groups earlier steps resolved (by their words), and tasks they took by place
    chosen: dict[str, list[str]] = Field(default_factory=dict[str, list[str]])
    taken: list[str] = Field(default_factory=list[str])


def ask(
    field: str, step: DraftStep, choices: list[Candidate], language: str, mention: str = ""
) -> Clarification:
    """Ask for one value in words, naming what was said and offering the choices."""
    label = field_label(field, language)
    if language == "zh":
        question = (
            f"「{mention}」对应多个{label}, 是哪一个?"
            if mention and len(choices) > 1
            else f"没找到叫「{mention}」的{label}, 是下面哪一个?"
            if mention and choices
            else f"没找到叫「{mention}」的{label}, 换个说法试试?"
            if mention
            else f"是哪个{label}?"
        )
    else:
        question = (
            f'"{mention}" matches several; which {label}?'
            if mention and len(choices) > 1
            else f'No {label} is called "{mention}"; is it one of these?'
            if mention and choices
            else f'No {label} is called "{mention}"; could you rephrase?'
            if mention
            else f"Which {label}?"
        )
    return Clarification(question=question, action=step.action, fields=[field], candidates=choices)


CONTAINER_KINDS = {
    "dataset_id": "dataset",
    "project_id": "project",
    "label_set_id": "label_set",
    "package_id": "package",
}


def named_in_words(field: str, state: FillState, catalog: EntityCatalog) -> str | None:
    """The one existing container of this kind the sentence names, if it names exactly one.

    Names win over the page: "Package 2 of 夜间行人" means that project's package even when
    the page shows another project.
    """
    kind = CONTAINER_KINDS.get(field)
    if kind is None or not state.text:
        return None
    named = {entry.id for entry in catalog.mentioned(kind, state.text)}
    return named.pop() if len(named) == 1 else None


def in_scope(field: str, value: object, state: FillState, catalog: EntityCatalog) -> str | None:
    """The container a value, the words or the page point at, in that order.

    ``value`` may be an id or the name the person used; a name that matches several
    containers is left to the caller to ask about.
    """
    kind = CONTAINER_KINDS[field]
    if isinstance(value, str) and value.strip():
        exact = catalog.get(kind, value)
        found = [exact] if exact is not None else catalog.match(kind, value)
        if len(found) == 1:
            return found[0].id
    return named_in_words(field, state, catalog) or context_value(field, state, catalog)


def project_in_scope(value: object, state: FillState, catalog: EntityCatalog) -> str | None:
    """The project a value, the words or the page point at, in that order."""
    return in_scope("project_id", value, state, catalog)


def context_value(field: str, state: FillState, catalog: EntityCatalog) -> str | None:
    """The page's (or the previous turn's) object for one container field."""
    context = state.context
    value: str | None = getattr(context, field, None)
    if value is None and field == "dataset_id" and context.version_id:
        version = catalog.get("version", context.version_id)
        value = version.parent if version else None
    if value is None and field == "dataset_id" and context.project_id:
        project = catalog.get("project", context.project_id)
        value = project.parent if project else None
    return value or state.focus.get(field)


BACK_KINDS = {**FIELD_KINDS, **LIST_KINDS, "task_ids": "task"}
# "刚才那个", "上一轮那几条", "it", "the same one": an object of the previous turn.
BACK = re.compile(
    r"^(?:刚才|刚刚|上一轮|上次|前面|上面)?(?:的)?(?:那个|那位|那条|那几条|那两条|那些|它|他|她|它们|他们)"
    r"(?:人|项目|模型|任务|标签集|角色|技能|团队|数据集|账号|包)?$"
    r"|^(?:it|them|that one|those|the same(?: one)?|him|her|that \w+)$",
    re.IGNORECASE,
)


def earlier_object(field: str, value: JsonValue, state: FillState) -> JsonValue:
    """The previous turn's object a back reference names; None when it names none."""
    if isinstance(value, list) and len(value) == 1:
        value = value[0]
    kind = BACK_KINDS.get(field)
    if kind is None or not isinstance(value, str) or not BACK.match(value.strip()):
        return None
    keys = [field, *(key for key in state.focus if BACK_KINDS.get(key) == kind)]
    found = next((state.focus[key] for key in keys if key in state.focus), None)
    listed: list[JsonValue] = [item for item in (found or "").split(",") if item]
    if not listed:
        return None
    if field.endswith("_ids"):
        return listed
    return {"$each": listed} if len(listed) > 1 and field == "task_id" else listed[0]
