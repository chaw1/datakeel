# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Validate the fixed paired evidence-query benchmark and its exact contract digest."""

import hashlib
from collections import Counter
from pathlib import Path
from typing import Self

import yaml
from pydantic import Field, model_validator

from datakeel.core.evidence_eval import QUESTION_KINDS, EvidenceThresholds, GoldTarget
from datakeel.core.models import BoundaryModel
from datakeel.harness.resources import contract_path
from datakeel.ontology.models import ObjectSet

MINIMUM_CATEGORY_QUESTIONS = 3
BASELINE_PROPERTIES = frozenset(
    {
        "id",
        "path",
        "filename",
        "modality",
        "size",
        "sha256",
        "quality",
        "created_at",
        "metadata.split",
        "metadata.annotation_categories",
        "metadata.annotation_available",
        "metadata.evidence_sample.annotation",
    }
)


class EvidenceQuestion(BoundaryModel):
    """Declare a label/property baseline and evidence query for one independent gold target."""

    id: str = Field(min_length=1)
    description: str = Field(min_length=1)
    baseline_description: str = Field(min_length=1)
    target: GoldTarget
    baseline: ObjectSet
    with_evidence: ObjectSet

    @model_validator(mode="after")
    def validate_queries(self) -> Self:
        """Keep benchmark queries unbound and prevent semantic evidence in the baseline."""
        if (
            self.baseline.assertion_filters
            or self.baseline.has_near_duplicate_in
            or any(rule.field not in BASELINE_PROPERTIES for rule in self.baseline.filters)
        ):
            msg = "Baseline queries may only use labels, paths, split, and quality"
            raise ValueError(msg)
        if (
            not self.with_evidence.assertion_filters
            and not self.with_evidence.has_near_duplicate_in
        ):
            msg = "Evidence queries must contain an assertion or direct-neighbor condition"
            raise ValueError(msg)
        for query in (self.baseline, self.with_evidence):
            if query.object_type != "file" or query.dataset_id or query.version_ids:
                msg = "Benchmark queries must be unbound file ObjectSets"
                raise ValueError(msg)
        return self


class EvidenceQuestionSuite(BoundaryModel):
    """Require fifteen unique questions and at least three per injected failure category."""

    schema_version: str = "1.0"
    thresholds: EvidenceThresholds = Field(default_factory=EvidenceThresholds)
    questions: tuple[EvidenceQuestion, ...] = Field(min_length=15, max_length=15)

    @model_validator(mode="after")
    def validate_coverage(self) -> Self:
        """Reject duplicated questions or a suite that omits an injection denominator."""
        if len({question.id for question in self.questions}) != len(self.questions):
            msg = "Evidence question identities must be unique"
            raise ValueError(msg)
        counts = Counter(question.target.kind for question in self.questions)
        if any(counts[kind] < MINIMUM_CATEGORY_QUESTIONS for kind in QUESTION_KINDS):
            msg = "Every injected category requires at least three questions"
            raise ValueError(msg)
        return self


def load_evidence_questions(path: Path | None = None) -> tuple[EvidenceQuestionSuite, str]:
    """Hash exact YAML bytes and parse the same source or installed-wheel contract."""
    content = (path or contract_path("evidence/questions.yaml")).read_bytes()
    return EvidenceQuestionSuite.model_validate(yaml.safe_load(content)), hashlib.sha256(
        content
    ).hexdigest()
