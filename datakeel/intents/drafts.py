# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Unchecked parse of one sentence, produced by rules or a model before validation."""

from typing import Literal

from pydantic import Field, JsonValue

from datakeel.core.models import BoundaryModel


class DraftStep(BoundaryModel):
    """One proposed action or read call; values may still be names or references."""

    id: str = Field(min_length=1, max_length=20)
    action: str = Field(min_length=1, max_length=100)
    params: dict[str, JsonValue] = Field(default_factory=dict)
    # The person's own words for each identity value, so a translated or abbreviated name
    # still counts as named (checked against the sentence, never trusted blindly).
    said: dict[str, str] = Field(default_factory=dict[str, str])


class SkippedPart(BoundaryModel):
    """A part of the request that is not planned, with the reason the person is told."""

    said: str = Field(default="", max_length=200)
    reason: str = Field(default="", max_length=300)
    # "checks" reasons are written by the planner itself; a model's own reason is never shown.
    source: Literal["model", "checks"] = "model"


def skipped_parts(value: JsonValue) -> list[JsonValue]:
    """The model's "skipped" list, keeping only {"said", "reason"} text pairs."""
    items = value if isinstance(value, list) else []
    return [
        {"said": str(item.get("said", ""))[:200], "reason": str(item.get("reason", ""))[:300]}
        for item in items[:10]
        if isinstance(item, dict)
    ]


class IntentDraft(BoundaryModel):
    """What the sentence asks for, before identities, scopes and schemas are checked."""

    kind: Literal["plan", "answer", "none"] = "none"
    reason: str = ""
    steps: list[DraftStep] = Field(default_factory=list[DraftStep], max_length=50)
    question: str = ""
    notes: list[str] = Field(default_factory=list[str])
    # With kind none: registered names the model found close to the request.
    related: list[str] = Field(default_factory=list[str], max_length=10)
    language: Literal["zh", "en"] = "zh"
    confident: bool = False
    # Parts of the request no step covers: each is reported, never dropped silently.
    skipped: list[SkippedPart] = Field(default_factory=list[SkippedPart], max_length=10)


def language_of(text: str) -> Literal["zh", "en"]:
    """Answer in Chinese when the sentence contains any CJK character."""
    return "zh" if any("一" <= char <= "鿿" for char in text) else "en"
