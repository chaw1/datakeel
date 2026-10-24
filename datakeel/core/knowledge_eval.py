# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Independent contracts for initial and reviewed knowledge-question evaluations."""

from typing import Literal

from pydantic import AwareDatetime, Field

from datakeel.core.ask_models import AskAnswer
from datakeel.core.models import BoundaryModel


class ExpectedClaim(BoundaryModel):
    """Require a documented triple and the independent state labels exposed to users."""

    head: str
    predicate: str
    tail: str
    relation_status: Literal["candidate", "accepted"] = "candidate"
    verification: Literal["verified", "needs_review"] = "verified"
    subject_link_status: Literal["candidate", "accepted"] | None = None
    subject_entity: str | None = None
    other_end_status: Literal["not_applicable", "linked", "not_in_catalog"] | None = None
    other_end_asset: str | None = None
    consistency: Literal["consistent", "not_in_system", "not_in_catalog"] | None = None


class KnowledgeExpectation(BoundaryModel):
    """Describe route-only counterexamples or exact semantic knowledge expectations."""

    answer_kind: Literal["metric", "knowledge"] = "knowledge"
    status: Literal["answered", "unanswerable", "clarification"] | None = "answered"
    subject: str | None = None
    system_assets: tuple[str, ...] = ()
    empty_system: bool = False
    claims: tuple[ExpectedClaim, ...] = ()
    forbidden_entities: tuple[str, ...] = ()
    forbidden_predicates: tuple[str, ...] = ()
    empty_claims: bool = False
    candidates: tuple[str, ...] = ()
    suggestions: bool = False
    reason_code: str | None = None
    pending_ambiguous_links: int | None = None
    gold_key: str | None = None


class KnowledgeQuestion(BoundaryModel):
    """Keep the two review-state outcomes next to one reusable user question."""

    id: str
    question: str
    initial: KnowledgeExpectation
    reviewed: KnowledgeExpectation | None = None


class KnowledgeQuestionSet(BoundaryModel):
    """Declare the knowledge suite separately from the original metric benchmark."""

    reference_instant: AwareDatetime
    questions: tuple[KnowledgeQuestion, ...] = Field(min_length=1)


class KnowledgeQuestionResult(BoundaryModel):
    """Preserve the actual production answer and concrete failed expectations."""

    id: str
    question: str
    passed: bool
    failures: tuple[str, ...] = ()
    answer: AskAnswer | None = None


class KnowledgeStateResult(BoundaryModel):
    """Group measurements by state without changing legacy metric denominators."""

    state: Literal["initial", "reviewed"]
    total: int
    passed: int
    questions: tuple[KnowledgeQuestionResult, ...]
    suite_digest: str


class KnowledgeEvaluation(BoundaryModel):
    """Require every knowledge and route-only case to pass in both states."""

    states: tuple[KnowledgeStateResult, ...]
    threshold_met: bool
    elapsed_seconds: float = Field(ge=0)
