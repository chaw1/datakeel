# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Independent gold, recorded outputs, and portable knowledge-graph evaluation reports."""

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import Field, JsonValue

from datakeel.core.models import BoundaryModel, new_id, utcnow


class GoldEntity(BoundaryModel):
    """Name a canonical gold entity and its scorer-only aliases."""

    name: str = Field(min_length=1)
    type: str = Field(min_length=1)
    aliases: tuple[str, ...] = ()


class GoldRelation(BoundaryModel):
    """Declare an oriented canonical triple without an extraction-derived anchor."""

    head: str = Field(min_length=1)
    relation: str = Field(min_length=1)
    tail: str = Field(min_length=1)

    boxes: tuple[tuple[float, float, float, float], ...] = ()

    def triple(self) -> tuple[str, str, str]:
        """Return the benchmark set identity."""
        return self.head, self.relation, self.tail


class KGCase(BoundaryModel):
    """Carry one independently labelled source passage."""

    id: str = Field(min_length=1)
    lang: Literal["zh", "en"]
    text: str = Field(min_length=1)
    entities: tuple[GoldEntity, ...]
    relations: tuple[GoldRelation, ...]
    optional: tuple[GoldRelation, ...] = ()
    traps: tuple[GoldRelation, ...] = ()


class KGCaseSuite(BoundaryModel):
    """Accept public or external same-schema evaluation cases."""

    id: str = Field(min_length=1)
    version: str = "1.0"
    cases: tuple[KGCase, ...] = Field(min_length=1)


class ScoredEntity(BoundaryModel):
    """Preserve raw predicted names and optional source spans without product normalization."""

    name: str
    type: str | None = None
    start: int | None = None
    end: int | None = None


class ScoredRelation(BoundaryModel):
    """Preserve the recording evidence fields and optional product verification flag."""

    head: str
    relation: str
    tail: str
    evidence: str | None = None
    ev_start: int | None = None
    ev_end: int | None = None
    head_span: tuple[int | None, int | None] | None = None
    tail_span: tuple[int | None, int | None] | None = None
    verification: Literal["verified", "needs_review"] | None = None
    regions: tuple[tuple[float, float, float, float], ...] = ()


class RecordedUsage(BoundaryModel):
    """Keep recorded usage separate from actual replay execution costs."""

    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)
    input_token_details: dict[str, JsonValue] = Field(default_factory=dict[str, JsonValue])
    output_token_details: dict[str, JsonValue] = Field(default_factory=dict[str, JsonValue])


class ScoredRecord(BoundaryModel):
    """Represent one passage's original or product-retained predictions."""

    pid: str
    entities: tuple[ScoredEntity, ...] = ()
    relations: tuple[ScoredRelation, ...] = ()
    latency_s: float = Field(default=0, ge=0)
    error: str | None = None
    usage: RecordedUsage | None = None
    failed_blocks: int = Field(default=0, ge=0)


class PRF(BoundaryModel):
    """Expose three-decimal benchmark precision, recall, F1, and exact counts."""

    p: float = Field(ge=0, le=1)
    r: float = Field(ge=0, le=1)
    f1: float = Field(ge=0, le=1)
    tp: int = Field(ge=0)
    fp: int = Field(ge=0)
    fn: int = Field(ge=0)


class KGMetrics(BoundaryModel):
    """Preserve the independent scorer's published denominators and supporting measurements."""

    passages: int
    missing: tuple[str, ...]
    errors: int
    relation_strict: PRF
    relation_pair: PRF
    entity_typed: PRF
    entity_untyped: PRF
    trap_hits: int
    pred_relations: int
    label_outside_schema: float
    endpoint_unmapped: int
    endpoint_in_text: float
    evidence_located: float
    verified_ratio: float
    failed_blocks: int
    latency_total_s: float
    latency_mean_s: float
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: Decimal | None = None


class KGScoringView(BoundaryModel):
    """Show all predictions, language slices, and the verification-only subset."""

    all: KGMetrics
    zh: KGMetrics
    en: KGMetrics
    verified: KGMetrics


class KGBlockedRelation(BoundaryModel):
    """Explain each relation excluded by the actual product pipeline."""

    case_id: str
    head: str
    relation: str
    tail: str
    evidence: str
    reason: str


class KGEvalFailure(BoundaryModel):
    """Identify an unsuccessful source block without copying its text or provider body."""

    case_id: str
    start: int = Field(ge=0)
    end: int = Field(ge=0)
    reason: str


class ImageGroupMetrics(BoundaryModel):
    """Report an explicit image group or language slice with geometric and text quality."""

    name: str
    metrics: KGMetrics
    box_true_positives: int = Field(ge=0)
    box_hits: int = Field(ge=0)
    box_hit_rate: float = Field(ge=0, le=1)
    cer: float | None = Field(default=None, ge=0)
    identifier_preservation: float | None = Field(default=None, ge=0, le=1)
    transcription_failures: int = Field(default=0, ge=0)


class ImageScoringView(BoundaryModel):
    """Keep clean, scan, diagram and bilingual slices in stable display order."""

    groups: tuple[ImageGroupMetrics, ...]


class KGEvalReport(BoundaryModel):
    """Persist independent recording and production-path scores from one execution."""

    schema_version: Literal["1.0"] = "1.0"
    suite: Literal["text", "image"] = "text"
    transcription_profile: str | None = None
    image_recording: ImageScoringView | None = None
    image_product: ImageScoringView | None = None
    id: str = Field(default_factory=new_id)
    provider: Literal["kg"] = "kg"
    created_at: datetime = Field(default_factory=utcnow)
    profile: str
    model: str
    suite_digest: str
    recording: KGScoringView
    product: KGScoringView
    blocked_relations: tuple[KGBlockedRelation, ...] = ()
    failures: tuple[KGEvalFailure, ...] = ()
    elapsed_seconds: float = Field(ge=0)
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    cost_usd: Decimal | None = None
    metric_convention: str = (
        "Independent benchmark normalization and aliases; tolerated triples contribute neither TP "
        "nor FP; unmapped endpoints count as FP; empty precision and recall are zero. "
        "Recording verification preserves original span checks; product verification uses the "
        "production evidence/head/tail checks. Recorded usage is not replay execution usage."
    )
