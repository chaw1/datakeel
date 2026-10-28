# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Render persisted annotation measurements into the rule-based analysis report."""

import json

from pydantic import JsonValue

from datakeel.core.annotation_models import ClassificationAgreement


def annotation_summary(details: dict[str, JsonValue]) -> str:
    """Describe agreement, suspected errors and signed inspection provenance."""
    classification = ClassificationAgreement.model_validate(details["classification"])
    lines = [
        f"Batch: {details['batch_id']}; version: {details['version_id']}.",
        f"Reviewed samples: {details['sample_count']}; coverage: {details['coverage']}.",
        (
            f"Fleiss kappa: {classification.fleiss_kappa.value}; "
            f"Krippendorff alpha: {classification.krippendorff_alpha.value}."
        ),
        *[
            f"{pair.annotator_a} / {pair.annotator_b}: "
            f"Cohen kappa {pair.cohen_kappa.value}; "
            f"raw agreement {pair.cohen_kappa.observed_agreement}."
            for pair in classification.pairs
        ],
        (
            f"Suspected rule findings: {details['suspected_findings']}. "
            "These require review and are not confirmed defects."
        ),
        f"Score rule: {details['rule']}",
    ]
    for field, label in (
        ("boxes", "Box agreement"),
        ("spans", "Span F1"),
        ("latest_inspection", "Approved inspection"),
        ("rework", "Rework comparison"),
    ):
        if details[field]:
            lines.append(f"{label}: {json.dumps(details[field], ensure_ascii=False)}")
    return "\n\n".join(lines)
