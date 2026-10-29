# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Persistent question threads, separate from model-driven Agent conversations."""

from pydantic import AwareDatetime

from datakeel.core.ask_frame_models import AskQueryFrame
from datakeel.core.ask_models import AskAnswer
from datakeel.core.models import BoundaryModel


class AskConversation(BoundaryModel):
    """Return an actor-owned question thread and its replayable turns."""

    id: str
    actor: str
    title: str
    created_at: AwareDatetime
    updated_at: AwareDatetime
    turns: tuple[AskAnswer, ...] = ()
    current_frame: AskQueryFrame | None = None
