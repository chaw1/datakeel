# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""One-sentence requests: page context, ordered action chains, clarifications and answers.

A chain only orders existing controlled-action plans. Every step is prepared as an ordinary
``ActionPlan`` and executed by a person through the same approval and execution services.
"""

from datetime import datetime
from typing import Literal

from pydantic import Field, JsonValue

from datakeel.core.models import BoundaryModel, new_id, utcnow

StepStatus = Literal["planned", "awaiting_approval", "running", "succeeded", "failed"]
ChainStatus = Literal["planned", "running", "awaiting_approval", "succeeded", "failed"]
IntentKind = Literal["plan", "answer", "clarify", "refuse", "unsupported"]
DetailTone = Literal["param", "default", "added", "removed", "impact"]
ParserKind = Literal["rules", "model"]


class PageContext(BoundaryModel):
    """Describe what the person is looking at when they type a request."""

    dataset_id: str | None = Field(default=None, max_length=200)
    version_id: str | None = Field(default=None, max_length=200)
    project_id: str | None = Field(default=None, max_length=200)
    package_id: str | None = Field(default=None, max_length=200)
    task_id: str | None = Field(default=None, max_length=200)
    label_set_id: str | None = Field(default=None, max_length=200)
    selected_kind: Literal["file", "production_task", "task_package"] | None = None
    selected_ids: tuple[str, ...] = Field(default=(), max_length=10000)


class StepEstimate(BoundaryModel):
    """Show what a step changes, what it costs and whether it needs a signature."""

    object_count: int | None = Field(default=None, ge=0)
    cost_usd: float = Field(default=0, ge=0, allow_inf_nan=False)
    requires_approval: bool = False
    external: bool = False
    exact: bool = False


class StepDetail(BoundaryModel):
    """One parameter of a step as a person reads it: names instead of ids, with counts."""

    label: str
    value: str
    tone: DetailTone = "param"


class ChainStep(BoundaryModel):
    """One existing controlled action, possibly fanned out over several targets.

    ``params`` may contain ``{"$ref": "<step id>.<output>"}`` values that resolve from an
    earlier step's receipt when this step is prepared. ``items`` lists per-target overrides.
    """

    id: str = Field(min_length=1, max_length=20)
    action: str = Field(min_length=1, max_length=100)
    params: dict[str, JsonValue] = Field(default_factory=dict)
    items: list[dict[str, JsonValue]] = Field(default_factory=list[dict[str, JsonValue]])
    scope: str = ""
    estimate: StepEstimate = Field(default_factory=StepEstimate)
    details: list[StepDetail] = Field(default_factory=list[StepDetail])
    status: StepStatus = "planned"
    attempts: int = Field(default=0, ge=0)
    plan_ids: list[str] = Field(default_factory=list[str])
    run_ids: list[str] = Field(default_factory=list[str])
    outputs: dict[str, JsonValue] = Field(default_factory=dict)
    error: str | None = None


class ActionChain(BoundaryModel):
    """Order existing action plans for one sentence and record each step's progress."""

    id: str = Field(default_factory=new_id)
    conversation_id: str | None = None
    actor: str = "local"
    text: str = ""
    language: Literal["zh", "en"] = "zh"
    parser: ParserKind = "rules"
    model: str | None = None
    steps: list[ChainStep] = Field(min_length=1, max_length=50)
    status: ChainStatus = "planned"
    notes: list[str] = Field(default_factory=list[str])
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class Candidate(BoundaryModel):
    """One object the person can pick when a mention is ambiguous."""

    id: str
    label: str
    kind: str


class Clarification(BoundaryModel):
    """Ask for a missing required value or a choice between named objects."""

    question: str
    action: str | None = None
    fields: list[str] = Field(default_factory=list[str])
    candidates: list[Candidate] = Field(default_factory=list[Candidate])


class ReadAnswer(BoundaryModel):
    """The read-only function that answered directly and its exact arguments."""

    function: str
    arguments: dict[str, JsonValue] = Field(default_factory=dict)
    data: JsonValue = None


class IntentResult(BoundaryModel):
    """What the one-sentence entry decided for this turn."""

    kind: IntentKind
    text: str
    parser: ParserKind = "rules"
    request: str = ""
    chain: ActionChain | None = None
    clarification: Clarification | None = None
    answer: ReadAnswer | None = None
    missing_scopes: list[str] = Field(default_factory=list[str])
    draft: dict[str, JsonValue] = Field(default_factory=dict)
