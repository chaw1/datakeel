# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Replayable questions, semantic matches, query evidence, and safe answer states."""

import unicodedata
from datetime import UTC, datetime
from typing import Literal, Self

from pydantic import AwareDatetime, Field, field_validator, model_validator

from datakeel.core.ask_chart_models import ChartSpec
from datakeel.core.ask_frame_models import AskComparison, AskQueryFrame
from datakeel.core.evidence_models import Assertion
from datakeel.core.knowledge_models import (
    KnowledgeAnswer,
    KnowledgeRecognition,
    KnowledgeSubject,
)
from datakeel.core.metric_models import (
    CompiledQuery,
    DimensionSlice,
    MetricCard,
    QueryResult,
    TimeRange,
)
from datakeel.core.models import BoundaryModel, new_id, utcnow
from datakeel.core.profile_models import ProfileAnswer

ASK_DATA_DESCRIPTION = (
    "Read metric values, owners, upstream or downstream; document evidence includes review status. "
    "Pass conversation_id from a prior answer to ask a follow-up question."
)


class MatchEvidence(BoundaryModel):
    """Locate a semantic match in NFC-normalized question code points."""

    start: int = Field(ge=0)
    end: int = Field(gt=0)
    text: str = Field(min_length=1)
    source: str = Field(min_length=1)
    match_kind: Literal["exact", "synonym", "normalized", "prefix", "dimension_value", "time"]
    metric_id: str | None = None
    dimension_id: str | None = None
    term_id: str | None = None
    value: str | None = None

    @model_validator(mode="after")
    def valid_span(self) -> Self:
        """Require a nonempty half-open span matching the captured text length."""
        if self.end - self.start != len(self.text):
            msg = "Match evidence span must equal captured text length"
            raise ValueError(msg)
        return self


class AskRequest(BoundaryModel):
    """Accept a local question and an explicitly injectable aware time reference."""

    question: str = Field(min_length=1, max_length=2000)
    metric_id: str | None = Field(default=None, min_length=1, max_length=200)
    subject_id: str | None = Field(default=None, min_length=1, max_length=500)
    knowledge_intent: Literal["owner", "upstream", "downstream", "owned"] | None = None
    session_id: str | None = Field(default=None, min_length=1, max_length=100)
    conversation_id: str | None = Field(default=None, min_length=1, max_length=100)
    reference_instant: AwareDatetime = Field(default_factory=utcnow)
    actor: str = Field(default="local-user", min_length=1, max_length=100)

    @field_validator("question")
    @classmethod
    def normalized_question(cls, value: str) -> str:
        """Normalize Unicode once so saved questions and evidence use the same offsets."""
        value = unicodedata.normalize("NFC", value)
        if not value.strip():
            msg = "Question must contain visible text"
            raise ValueError(msg)
        return value

    @field_validator("reference_instant")
    @classmethod
    def utc_reference(cls, value: datetime) -> datetime:
        """Represent injected time references consistently in UTC."""
        return value.astimezone(UTC)


class LineageReference(BoundaryModel):
    """Identify the bounded catalog subgraph supporting an answer."""

    asset_id: str
    hops: int = Field(default=2, ge=0, le=3)
    max_nodes: int = Field(default=30, ge=1, le=100)
    include_catalog: Literal[True] = True


class AskInterpretation(BoundaryModel):
    """Record how a numeric question was understood, including fragments left unexplained."""

    metric_id: str | None = None
    time_range: TimeRange | None = None
    time_basis: Literal["period", "as_of"] | None = None
    slices: tuple[DimensionSlice, ...] = ()
    group_by: tuple[str, ...] = ()
    unconsumed: tuple[str, ...] = ()


class AskAnswer(BoundaryModel):
    """Persist one fully evidenced answer, refusal, or request for clarification."""

    id: str = Field(default_factory=new_id)
    session_id: str
    question: str
    status: Literal["answered", "unanswerable", "clarification"]
    message: str
    reference_instant: AwareDatetime
    conversation_id: str | None = None
    interpreted_question: str = ""
    interpreted_question_en: str = Field(
        default="",
        description="The same interpretation in English, for an English interface.",
        exclude_if=lambda value: not value,
    )
    query_frame: AskQueryFrame | None = None
    comparison: AskComparison | None = None
    chart: ChartSpec | None = Field(default=None, exclude_if=lambda value: value is None)
    metric_card: MetricCard | None = None
    sql: CompiledQuery | None = None
    result: QueryResult | None = None
    time_range: TimeRange | None = None
    matches: tuple[MatchEvidence, ...] = ()
    candidates: tuple[MetricCard, ...] = ()
    lineage: LineageReference | None = None
    assertion_ids: tuple[str, ...] = ()
    assertions: tuple[Assertion, ...] = ()
    answer_kind: Literal["metric", "knowledge", "profile"] = "metric"
    knowledge: KnowledgeAnswer | None = None
    subject_candidates: tuple[KnowledgeSubject, ...] = ()
    recognition: KnowledgeRecognition | None = None
    profile: ProfileAnswer | None = Field(default=None, exclude_if=lambda value: value is None)
    interpretation: AskInterpretation | None = Field(
        default=None, exclude_if=lambda value: value is None
    )

    @model_validator(mode="after")
    def evidence_matches_state(self) -> Self:
        """Forbid guessed values and ensure every text anchor addresses the saved question."""
        if self.answer_kind == "profile":
            self._validate_profile()
            return self
        if self.profile is not None:
            msg = "Profile measurements require the profile answer kind"
            raise ValueError(msg)
        if self.answer_kind == "knowledge":
            self._validate_knowledge()
            return self
        if self.question != unicodedata.normalize("NFC", self.question):
            msg = "Saved questions must use NFC normalization"
            raise ValueError(msg)
        if any(self.question[item.start : item.end] != item.text for item in self.matches):
            msg = "Match evidence does not address the saved question"
            raise ValueError(msg)
        if self.status != "answered":
            if self.sql is not None or self.result is not None or self.metric_card is not None:
                msg = "Non-answer states must never include SQL, results, or an asserted metric"
                raise ValueError(msg)
        else:
            self._validate_answer()
        return self

    def _validate_profile(self) -> None:
        if not unicodedata.is_normalized("NFC", self.question) or any(
            self.question[item.start : item.end] != item.text for item in self.matches
        ):
            msg = "Profile match evidence must address the normalized question"
            raise ValueError(msg)
        if self.profile is None or any(
            value is not None for value in (self.sql, self.result, self.metric_card, self.knowledge)
        ):
            msg = "Profile answers require only a typed profile payload"
            raise ValueError(msg)
        profile = self.profile
        if self.status != "answered":
            if profile.ranking or profile.reason_code is None:
                msg = "Non-answer profile states cannot assert numeric rankings"
                raise ValueError(msg)
            if self.status == "clarification" and len(profile.candidates) <= 1:
                msg = "Profile clarification requires multiple dataset candidates"
                raise ValueError(msg)
            return
        if profile.dataset is None or not profile.ranking or profile.reason_code is not None:
            msg = "Answered profile questions require a dataset and measured interval ranking"
            raise ValueError(msg)
        if len({rank.device for rank in profile.ranking}) != len(profile.ranking):
            msg = "Profile rankings require distinct devices"
            raise ValueError(msg)
        if any(
            (item.dataset_id, item.version_id)
            != (profile.dataset.dataset_id, profile.dataset.version_id)
            for rank in profile.ranking
            for item in rank.evidence
        ):
            msg = "Profile evidence must match the selected published dataset version"
            raise ValueError(msg)

    def _validate_knowledge(self) -> None:
        if not unicodedata.is_normalized("NFC", self.question):
            msg = "Knowledge questions must use NFC normalization"
            raise ValueError(msg)
        if not all(item.text == self.question[item.start : item.end] for item in self.matches):
            msg = "Knowledge match evidence does not address the saved question"
            raise ValueError(msg)
        if self.knowledge is None:
            msg = "Knowledge answers require a typed knowledge payload"
            raise ValueError(msg)
        if any(value is not None for value in (self.sql, self.result, self.metric_card)):
            msg = "Knowledge answers cannot contain metric execution results"
            raise ValueError(msg)
        if self.status == "answered" and (
            self.knowledge.subject is None
            or not (self.knowledge.system_records or self.knowledge.claims)
        ):
            msg = "Answered knowledge questions require a subject and at least one fact"
            raise ValueError(msg)
        if (
            self.status == "clarification"
            and len(self.subject_candidates) <= 1
            and len(self.knowledge.intent_candidates) <= 1
        ):
            msg = "Knowledge clarification requires multiple subject or intent candidates"
            raise ValueError(msg)
        if self.status == "unanswerable" and self.knowledge.reason_code is None:
            msg = "Knowledge refusals require an explicit reason code"
            raise ValueError(msg)

    def _validate_answer(self) -> None:
        if (
            self.metric_card is None
            or self.sql is None
            or self.result is None
            or self.lineage is None
        ):
            msg = "Answered questions require a metric card, SQL, result, and lineage reference"
            raise ValueError(msg)
        metric = self.metric_card.definition
        if (metric.id, metric.version) != (self.sql.metric_id, self.sql.metric_version):
            msg = "Answer metric and compiled query revisions must agree"
            raise ValueError(msg)
        if not self.sql.tables or not self.sql.columns or not self.matches:
            msg = "Answered questions require table, column, and text-match evidence"
            raise ValueError(msg)


class ParsedQuestion(BoundaryModel):
    """Carry pure parsing evidence without selecting SQL or executing a source."""

    question: str
    matches: tuple[MatchEvidence, ...] = ()
    time_range: TimeRange | None = None
    issues: tuple[str, ...] = ()


class MetricResolution(BoundaryModel):
    """Record deterministic candidate selection and its explainable outcome."""

    status: Literal["resolved", "unanswerable", "clarification"]
    candidates: tuple[MetricCard, ...]
    message: str


class CandidateOrder(BoundaryModel):
    """Limit optional model output to a permutation of supplied candidate identities."""

    ordered_ids: tuple[str, ...]


class RerankRequest(BoundaryModel):
    """Expose candidate identities to a provider without any SQL-writing interface."""

    question: str
    candidate_ids: tuple[str, ...]
