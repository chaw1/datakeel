# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Combine P26 suspicion findings, template checks and draft disagreement into one risk score.

Each rule hit carries a fixed weight read as the chance that the hit alone means the task
needs a human fix. Independent hits combine by noisy-OR, ``1 - prod(1 - weight)``, so the
score stays in [0, 1], never falls when another hit is added, and one strong hit outranks
several weak ones. A task is high risk at 0.3 or above; every listed rule except the rare
category rule reaches that alone.
"""

import hashlib
import re
from collections.abc import Sequence

from datakeel.core.annotation_models import AnnotationFinding
from datakeel.core.prelabel_models import ObjectRef, RiskReason

HIGH_RISK = 0.3
RULE_WEIGHTS: dict[str, float] = {
    "template_violation": 0.9,
    "invalid_bbox": 0.9,
    "invalid_span": 0.9,
    "minority_label": 0.7,
    "multilabel_conflict": 0.6,
    "near_duplicate_conflict": 0.6,
    "bbox_category_minority": 0.6,
    "span_category_minority": 0.6,
    "bbox_size_outlier": 0.5,
    "bbox_missing": 0.5,
    "bbox_extra": 0.5,
    "span_missing": 0.5,
    "span_extra": 0.5,
    "duplicate_bbox": 0.5,
    "duplicate_span": 0.5,
    "bbox_aspect_outlier": 0.4,
    "span_length_outlier": 0.4,
    "span_boundary_minority": 0.4,
    "rare_category": 0.2,
}
DISAGREEMENT_WEIGHT = 0.5
_LOCATION = re.compile(r"\b(box|span|polygon)\[(\d+)\]")
_DRAW_DIGITS = 13


def noisy_or(weights: Sequence[float]) -> float:
    """Combine independent hit weights; no hits score zero."""
    remaining = 1.0
    for weight in weights:
        remaining *= 1 - weight
    return round(1 - remaining, 6)


def finding_objects(finding: AnnotationFinding) -> tuple[ObjectRef, ...]:
    """Locate the boxes or spans a finding names in its evidence, such as ``box[2]``."""
    found = dict.fromkeys(
        (kind, int(index)) for text in finding.evidence for kind, index in _LOCATION.findall(text)
    )
    if not found and finding.code in {"minority_label", "multilabel_conflict", "rare_category"}:
        found = {("label_set", 0): None}
    return tuple(ObjectRef.model_validate({"kind": kind, "index": index}) for kind, index in found)


def finding_reason(finding: AnnotationFinding) -> RiskReason:
    """Turn one P26 finding into a weighted, locatable risk reason."""
    return RiskReason(
        code=finding.code,
        weight=RULE_WEIGHTS.get(finding.code, 0.3),
        message=finding.reason,
        evidence=finding.evidence[:4],
        objects=finding_objects(finding),
    )


def disagreement_reason(
    confidence: float, difference: float, objects: tuple[ObjectRef, ...]
) -> RiskReason | None:
    """Flag a human head that departs from a confident model draft."""
    weight = round(DISAGREEMENT_WEIGHT * confidence * difference, 6)
    if weight <= 0:
        return None
    return RiskReason(
        code="prelabel_disagreement",
        weight=min(weight, 1.0),
        message="The submitted annotation departs from a confident model draft",
        evidence=(f"model_confidence={confidence:.3f}; difference={difference:.3f}",),
        objects=objects,
    )


def risk_score(reasons: Sequence[RiskReason]) -> float:
    """Score all reasons together by noisy-OR."""
    return noisy_or([reason.weight for reason in reasons])


def sample_draw(task_id: str, round_number: int, revision_id: str) -> float:
    """Draw a reproducible uniform value in [0, 1) for review sampling of one submission."""
    digest = hashlib.sha256(f"{task_id}:{round_number}:{revision_id}".encode()).hexdigest()
    return int(digest[:_DRAW_DIGITS], 16) / 16**_DRAW_DIGITS
