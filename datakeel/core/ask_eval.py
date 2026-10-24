# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Typed question benchmarks and truthful provider=ask evaluation reports."""

from datetime import datetime
from typing import Literal, Self

from pydantic import AwareDatetime, Field, model_validator

from datakeel.core.ask_models import AskAnswer
from datakeel.core.knowledge_eval import KnowledgeEvaluation
from datakeel.core.metric_models import QueryResult
from datakeel.core.models import BoundaryModel, new_id, utcnow


class AskQuestion(BoundaryModel):
    """Declare one independent expected status and optional scalar or table gold."""

    id: str
    question: str
    expected_status: Literal["answered", "unanswerable", "clarification"]
    metric_id: str | None = None
    gold_key: str | None = None
    expected_table: QueryResult | None = None

    @model_validator(mode="after")
    def valid_gold(self) -> Self:
        """Answerable cases require a metric and exactly one kind of independent gold."""
        if self.expected_status == "answered" and (
            not self.metric_id or (self.gold_key is None) == (self.expected_table is None)
        ):
            msg = "Answered cases require a metric and exactly one scalar key or table gold"
            raise ValueError(msg)
        return self


class AskQuestionSet(BoundaryModel):
    """Bind benchmark questions to a fixed aware reference instant."""

    reference_instant: AwareDatetime
    questions: tuple[AskQuestion, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_cases(self) -> Self:
        """Keep case identities unique and table questions inside the declared scope."""
        identities = [item.id for item in self.questions]
        if len(identities) != len(set(identities)):
            msg = "Question identities must be unique"
            raise ValueError(msg)
        table_limit = 2
        if sum(item.expected_table is not None for item in self.questions) > table_limit:
            msg = "Question suites may contain at most two table answers"
            raise ValueError(msg)
        return self


class AskQuestionResult(BoundaryModel):
    """Retain actual answer evidence alongside independent correctness measurements."""

    id: str
    expected_status: Literal["answered", "unanswerable", "clarification"]
    actual_status: Literal["answered", "unanswerable", "clarification", "error"]
    correct: bool
    evidence_complete: bool
    expected_value: float | None = None
    answer: AskAnswer | None = None
    error: str | None = None


class AskThresholds(BoundaryModel):
    """Publish reporting targets separately from process success and quality gates."""

    minimum_correct: int = Field(default=13, ge=0)
    required_refusals: int = Field(default=4, ge=0)
    required_evidence: int = Field(default=20, ge=0)
    relative_tolerance: float = Field(default=0.005, ge=0, le=1)


class AskEvalReport(BoundaryModel):
    """Persist measured benchmark results without treating report thresholds as CI gates."""

    schema_version: Literal["1.0"] = "1.0"
    id: str = Field(default_factory=new_id)
    provider: Literal["ask"] = "ask"
    created_at: datetime = Field(default_factory=utcnow)
    reference_instant: AwareDatetime
    suite_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    gold_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    questions: tuple[AskQuestionResult, ...]
    answerable: int
    correct: int
    accuracy: float
    unanswerable: int
    refused: int
    refusal_rate: float
    clarification: int
    clarified: int
    evidence_complete: int
    evidence_rate: float
    thresholds: AskThresholds = Field(default_factory=AskThresholds)
    threshold_met: bool
    evaluation_seconds: float = Field(ge=0)
    knowledge: KnowledgeEvaluation | None = None
    evidence_convention: str = (
        "Answered: card, SELECT, tables, columns, matches and assertions; "
        "unanswerable: three suggestions and refusal assertions; "
        "clarification: at least two candidates and matching assertions."
    )
