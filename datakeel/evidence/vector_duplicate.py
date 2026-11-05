# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Exact F64 cosine over canonical F32 outputs with canonical direct-pair anchors."""

import math

from datakeel.core.evidence_drafts import ObservationDraft
from datakeel.core.evidence_models import EvidenceAnchor, ExtractorRef
from datakeel.core.vector_models import DuplicateParams, VectorCounts, VectorError, vector_hash
from datakeel.core.vector_results import CosineMeasurement, VectorPair, VectorSample


def global_key(samples: tuple[VectorSample, ...], params: DuplicateParams) -> str:
    """Bind the full target/revision/content/vector/status summary, independent of input order."""
    return vector_hash(
        {
            "contract": "we-e2-duplicate-v1",
            "mode": "fake",
            "implementation": "we-e2-fake-v1",
            "params": params.model_dump(mode="json"),
            "targets": sorted(sample.canonical() for sample in samples),
        }
    )


def direct_pairs(
    samples: tuple[VectorSample, ...], params: DuplicateParams
) -> tuple[VectorPair, ...]:
    """Evaluate every i<j directly; never infer edges from another candidate pair."""
    valid = sorted(
        (sample for sample in samples if sample.failure is None),
        key=lambda sample: sample.subject.asset_id,
    )
    if (
        len(samples) > params.max_samples
        or len(valid) * (len(valid) - 1) // 2 > params.max_candidate_pairs
    ):
        msg = "vector_capacity_exceeded"
        raise VectorError(msg)
    pairs: list[VectorPair] = []
    for index, left in enumerate(valid):
        for right in valid[index + 1 :]:
            if len(left.vector) != len(right.vector):
                msg = "vector_dimension_mismatch"
                raise VectorError(msg)
            dot = math.fsum(a * b for a, b in zip(left.vector, right.vector, strict=True))
            norm = math.sqrt(math.fsum(a * a for a in left.vector)) * math.sqrt(
                math.fsum(b * b for b in right.vector)
            )
            similarity = max(-1.0, min(1.0, dot / norm))
            if similarity >= params.threshold:
                pairs.append(
                    VectorPair(
                        left=left.subject.asset_id,
                        right=right.subject.asset_id,
                        measurement=CosineMeasurement(
                            similarity=similarity, threshold=params.threshold
                        ),
                    )
                )
    return tuple(pairs)


def vector_counts(samples: tuple[VectorSample, ...]) -> VectorCounts:
    """Count typed failures even on a completely hot cache."""
    failed = sum(sample.failure is not None for sample in samples)
    return VectorCounts(input=len(samples), eligible=len(samples) - failed, failed=failed)


def pair_drafts(
    samples: tuple[VectorSample, ...], pairs: tuple[VectorPair, ...]
) -> tuple[ObservationDraft, ...]:
    """Bind both Whole anchors to original bytes, never preprocessed or peer-only hashes."""
    by_id = {sample.subject.asset_id: sample for sample in samples}
    return tuple(
        ObservationDraft(
            subject=by_id[pair.left].subject,
            predicate="semantic_duplicate_of",
            object=by_id[pair.right].subject,
            anchors=tuple(
                EvidenceAnchor(
                    asset_ref=by_id[key].subject, content_revision=by_id[key].content_revision
                )
                for key in (pair.left, pair.right)
            ),
            extractor=ExtractorRef(id="evidence.semantic_duplicate", version="we-e2-fake-v1"),
            measurement=pair.measurement,
            reason="fake_contract_candidate_not_model_quality",
        )
        for pair in pairs
    )
