# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""What the person is looking at when they speak, as the planner shows it to a model."""

import json

from pydantic import Field

from datakeel.core.intent_models import PageContext
from datakeel.core.models import BoundaryModel


class PlannerScene(BoundaryModel):
    """What the person is looking at, what the previous turn touched and any open question."""

    context: PageContext = Field(default_factory=PageContext)
    focus: dict[str, str] = Field(default_factory=dict[str, str])
    open_request: str = ""
    open_question: str = ""
    speaker: str = ""
    roles: list[str] = Field(default_factory=list[str])


def scene_text(scene: PlannerScene) -> str:
    """The speaker, the page, the previous turn and any open question, for the model."""
    text = (
        "\nSpeaker id: "
        + scene.speaker
        + ("\nSpeaker roles: " + ", ".join(scene.roles) if scene.roles else "")
        + "\nPage context: "
        + scene.context.model_dump_json(exclude_defaults=True)
        + "\nPrevious turn objects: "
        + json.dumps(scene.focus, ensure_ascii=False)
    )
    if scene.open_request:
        text += (
            "\nUnfinished earlier request: "
            + scene.open_request
            + "\nYou asked: "
            + scene.open_question
            + "\nIf the new message answers that question, return the complete plan for the "
            "earlier request with the answer applied; otherwise plan the new message alone."
        )
    return text
