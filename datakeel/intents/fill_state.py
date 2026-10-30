# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""What every step is filled from (page, previous turn, speaker) and how a value is asked."""

from pydantic import Field

from datakeel.core.intent_models import Candidate, Clarification, PageContext
from datakeel.core.models import BoundaryModel
from datakeel.intents.catalog import EntityCatalog
from datakeel.intents.drafts import DraftStep
from datakeel.intents.wording import field_label


class FillState(BoundaryModel):
    """Values available to every step: page context and the previous turn's objects."""

    context: PageContext = Field(default_factory=PageContext)
    focus: dict[str, str] = Field(default_factory=dict[str, str])
    actor: str = "local"
    language: str = "zh"
    text: str = ""


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
