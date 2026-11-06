# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Convert deterministic set measurements to anchored candidate drafts without side effects."""

from datakeel.core.evidence_drafts import ObservationDraft
from datakeel.core.evidence_models import EvidenceAnchor, EvidenceValue, ExtractorRef
from datakeel.core.vector_measurements import CoverageMeasurement
from datakeel.core.vector_results import VectorFinding, VectorSample


def set_drafts(
    samples: tuple[VectorSample, ...], findings: tuple[VectorFinding, ...], operator: str
) -> tuple[ObservationDraft, ...]:
    """Anchor a subject and nearest R while retaining the full closure in its measurement."""
    by_id = {s.subject.asset_id: s for s in samples}
    result: list[ObservationDraft] = []
    predicates = {
        "evidence.semantic_cluster": "semantic_cluster_member",
        "evidence.semantic_outlier": "semantic_outlier",
        "evidence.coverage_gap": "coverage_gap",
    }
    for finding in findings:
        sample = by_id[finding.subject]
        anchored = [sample]
        if isinstance(finding.measurement, CoverageMeasurement):
            anchored.append(by_id[finding.measurement.nearest.asset_id])
        result.append(
            ObservationDraft(
                subject=sample.subject,
                predicate=predicates[operator],
                object=finding.object or EvidenceValue(concept="dbscan_noise", value="present"),
                anchors=tuple(
                    EvidenceAnchor(asset_ref=s.subject, content_revision=s.content_revision)
                    for s in anchored
                ),
                extractor=ExtractorRef(id=operator, version="we-e3-sets-v1"),
                measurement=finding.measurement,
                reason="fake_candidate_relative_to_frozen_references"
                if operator == "evidence.coverage_gap"
                else "fake_contract_candidate_not_model_quality",
            )
        )
    return tuple(result)
