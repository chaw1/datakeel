# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Frozen contracts for offline, record-level training data governance."""

from typing import Literal

from pydantic import Field, JsonValue

from datakeel.core.models import BoundaryModel

TrainingFormat = Literal["auto", "messages", "instruction", "preference"]


class TrainingConfig(BoundaryModel):
    """Freeze all rule thresholds so a dry run can be reproduced exactly."""

    format: TrainingFormat = "auto"
    max_tokens: int = Field(default=8192, ge=1, le=1000000)
    near_distance: int = Field(default=8, ge=0, le=16)
    near_similarity: float = Field(default=0.9, ge=0, le=1)
    repetition_threshold: float = Field(default=0.45, ge=0, le=1)
    contamination_ngram: int = Field(default=13, ge=2, le=100)
    contamination_threshold: float = Field(default=0.2, gt=0, le=1)
    refusal_phrases: tuple[str, ...] = (
        "as an ai language model",
        "as an artificial intelligence",
        "i cannot assist with",
        "作为一个ai",
        "作为人工智能",
        "作为一个人工智能",
        "我无法协助",
    )
    sample_limit: int = Field(default=50, ge=0, le=200)
    max_line_bytes: int = Field(default=1048576, ge=1024, le=16777216)


class TrainingSource(BoundaryModel):
    """Identify one explicitly selected local JSONL source without loading its contents."""

    file_id: str
    path: str
    filename: str


class TrainingIssue(BoundaryModel):
    """Locate a measured rule signal; evidence is always redacted for presentation."""

    code: str
    field: str = "record"
    message: str
    evidence: str = ""
    start: int | None = None
    end: int | None = None
    related_id: str | None = None


class TrainingRecord(BoundaryModel):
    """Carry a bounded, redacted record preview and its stable source identity."""

    id: str
    file_id: str
    line: int
    content_hash: str
    format: TrainingFormat
    language: Literal["zh", "en", "mixed", "unknown"] = "unknown"
    language_confidence: float = 0
    estimated_tokens: int = 0
    preview: str = ""
    issues: tuple[TrainingIssue, ...] = ()
    decision: Literal["keep", "drop", "redact"] = "keep"
    reasons: tuple[str, ...] = ()


class TrainingFileSummary(BoundaryModel):
    """Aggregate one source without retaining every parsed record in memory."""

    file_id: str
    filename: str
    records: int
    valid_records: int
    issue_counts: dict[str, int] = Field(default_factory=dict)


class TrainingReport(BoundaryModel):
    """Expose deterministic counts and bounded samples; the full ledger stays on disk."""

    rule_version: str = "1.0"
    config: TrainingConfig
    records: int = 0
    valid_records: int = 0
    issue_counts: dict[str, int] = Field(default_factory=dict)
    languages: dict[str, int] = Field(default_factory=dict)
    formats: dict[str, int] = Field(default_factory=dict)
    files: tuple[TrainingFileSummary, ...] = ()
    samples: tuple[TrainingRecord, ...] = ()
    duplicate_clusters: tuple[tuple[str, ...], ...] = ()
    contamination_hits: tuple[TrainingIssue, ...] = ()
    chosen_longer_ratio: float = 0
    preference_records: int = 0
    dropped: int = 0
    redacted: int = 0
    pii_records: int = 0
    kept: int = 0
    ledger_sha256: str = ""
    source_sha256: dict[str, str] = Field(default_factory=dict)
    evaluation_sha256: dict[str, str] = Field(default_factory=dict)
    dedup_backend: str = "python"


class ParsedTrainingRecord(BoundaryModel):
    """Keep a single raw record inside the streaming engine, never in public reports."""

    format: TrainingFormat
    payload: dict[str, JsonValue]
    prompt: str
    answer: str
    text: str
    rejected: str = ""
    issues: tuple[TrainingIssue, ...] = ()
