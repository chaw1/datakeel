# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Typed benchmark denominators, retrieval measurements, and persisted evidence reports."""

from datetime import datetime
from typing import Literal

from pydantic import Field

from datakeel.core.evidence_execution import EvidenceRunReport
from datakeel.core.models import BoundaryModel, new_id, utcnow

QuestionKind = Literal["near_duplicate", "conflict", "corrupt", "missing_annotation"]
QUESTION_KINDS: tuple[QuestionKind, ...] = (
    "near_duplicate",
    "conflict",
    "corrupt",
    "missing_annotation",
)


class GoldTarget(BoundaryModel):
    """Declare an independent ground-truth subset rather than a query-derived answer."""

    kind: QuestionKind
    split: Literal["train", "val"] | None = None
    concept: str | None = None
    scene: str | None = None
    peer_split: Literal["train", "val"] | None = None


class RetrievalMetrics(BoundaryModel):
    """Expose actual set counts and ratios; empty predictions have precision zero."""

    selected: int = Field(ge=0)
    expected: int = Field(ge=0)
    true_positive: int = Field(ge=0)
    false_positive: int = Field(ge=0)
    false_negative: int = Field(ge=0)
    precision: float = Field(ge=0, le=1)
    recall: float = Field(ge=0, le=1)


class MacroMetrics(BoundaryModel):
    """Weight every fixed question equally, including questions with empty gold sets."""

    precision: float = Field(ge=0, le=1)
    recall: float = Field(ge=0, le=1)


class EvidenceQuestionResult(BoundaryModel):
    """Compare both executable selections against the same independent denominator."""

    id: str
    description: str
    baseline_description: str
    kind: QuestionKind
    baseline: RetrievalMetrics
    with_evidence: RetrievalMetrics


class EvidenceThresholds(BoundaryModel):
    """Keep the published comparison targets separate from command success or CI gates."""

    recall_gain: float = Field(default=0.05, ge=0, le=1)
    allowed_precision_drop: float = Field(default=0.02, ge=0, le=1)
    pair_precision: float = Field(default=0.9, ge=0, le=1)
    pair_recall: float = Field(default=0.8, ge=0, le=1)


class PresenceCounts(BoundaryModel):
    """Count actual active candidate/accepted assertions without synthesizing states."""

    present: int = Field(default=0, ge=0)
    absent: int = Field(default=0, ge=0)
    unknown: int = Field(default=0, ge=0)


class EvidenceEvalReport(BoundaryModel):
    """Persist truthful evidence measurements in the existing eval_runs relation."""

    schema_version: Literal["1.0"] = "1.0"
    id: str = Field(default_factory=new_id)
    provider: Literal["evidence"] = "evidence"
    created_at: datetime = Field(default_factory=utcnow)
    suite_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    gold_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    dataset_id: str
    source_version: str
    sample_count: int = Field(ge=1)
    questions: tuple[EvidenceQuestionResult, ...] = Field(min_length=15, max_length=15)
    baseline_macro: MacroMetrics
    with_evidence_macro: MacroMetrics
    near_duplicate_pairs: RetrievalMetrics
    near_duplicate_mode: Literal["prefix", "exact"] = "prefix"
    val_to_train_pairs: RetrievalMetrics
    presence_counts: PresenceCounts
    extraction: EvidenceRunReport
    extraction_scope: Literal["fresh", "existing"]
    evaluation_seconds: float = Field(ge=0)
    benchmark_seconds: float | None = Field(default=None, ge=0)
    thresholds: EvidenceThresholds
    threshold_met: bool
    metric_convention: str = "Empty prediction precision = 0; empty gold recall = 1."
