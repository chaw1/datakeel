# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Pure annotation quality evaluation and deterministic suspicion assembly."""

from datakeel.annotation_qa.classification import classification_agreement
from datakeel.annotation_qa.consensus import consensus_findings
from datakeel.annotation_qa.findings import (
    duplicate_findings,
    minority_findings,
    structural_findings,
)
from datakeel.annotation_qa.geometry import box_agreement, span_agreement
from datakeel.annotation_qa.labels import multiselect_findings, rare_category_findings
from datakeel.annotation_qa.outliers import box_outliers, span_outliers
from datakeel.core.annotation_models import AnnotationBatch, AnnotationFinding, AnnotationQAResult


def find_suspicions(batch: AnnotationBatch) -> tuple[AnnotationFinding, ...]:
    """Collect conservative statistical/rule review candidates in stable identity order."""
    candidates = {
        item.finding_id: item
        for rule in (
            minority_findings,
            duplicate_findings,
            structural_findings,
            multiselect_findings,
            consensus_findings,
            box_outliers,
            span_outliers,
            rare_category_findings,
        )
        for item in rule(batch)
    }
    return tuple(
        sorted(candidates.values(), key=lambda item: (item.sample_id, item.code, item.finding_id))
    )


def evaluate_annotations(batch: AnnotationBatch) -> AnnotationQAResult:
    """Evaluate one frozen batch without storage, network calls or model providers."""
    return AnnotationQAResult(
        classification=classification_agreement(batch),
        boxes=box_agreement(batch),
        spans=span_agreement(batch),
        findings=find_suspicions(batch),
        sample_count=len({item.sample_id for item in batch.annotations}),
        annotator_count=len({item.annotator_id for item in batch.annotations}),
    )
