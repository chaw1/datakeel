# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Public version-pinned training governance and evaluation registration contracts."""

from datetime import datetime

from pydantic import Field

from datakeel.core.llm_data_models import TrainingConfig, TrainingReport
from datakeel.core.models import BoundaryModel

TRAINING_QUALITY_DESCRIPTION = (
    "Read offline SFT messages, instruction and preference JSONL training quality findings: "
    "format, duplicates, PII, languages and registered evaluation contamination. "
    "训练数据治理、对话与偏好数据质量问题; 只读检查, 不执行清洗。"
)


class TrainingAnalysisRequest(BoundaryModel):
    """Analyze selected uploaded JSONL files with a completely frozen rule configuration."""

    version_id: str | None = None
    file_ids: tuple[str, ...] = Field(default=(), max_length=10000)
    evaluation_ids: tuple[str, ...] = Field(default=(), max_length=100)
    config: TrainingConfig = Field(default_factory=TrainingConfig)


class TrainingEvaluationRequest(BoundaryModel):
    """Register evaluation files from an existing uploaded dataset, never an arbitrary path."""

    name: str = Field(min_length=1, max_length=200)
    source_dataset_id: str = Field(min_length=1)
    version_id: str | None = None
    file_ids: tuple[str, ...] = Field(min_length=1, max_length=1000)


class TrainingEvaluation(BoundaryModel):
    """Identify an immutable user-registered evaluation snapshot."""

    id: str
    dataset_id: str
    name: str
    source_dataset_id: str
    version_id: str
    file_ids: tuple[str, ...]
    created_at: datetime


class TrainingGovernanceRun(BoundaryModel):
    """Present bounded redacted findings and the complete decision-ledger fingerprint."""

    id: str
    dataset_id: str
    version_id: str
    created_at: datetime
    report: TrainingReport
    ledger_sha256: str
    cleaned_version_id: str | None = None


class TrainingQualityQuery(BoundaryModel):
    """Read the latest recorded training analysis for one exact dataset version."""

    dataset_id: str = Field(min_length=1)
    version_id: str | None = None
