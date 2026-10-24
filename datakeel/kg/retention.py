# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Preserve unaffected evidence when only selected documents finish re-extraction."""

from datakeel.core.evidence_drafts import ObservationDraft
from datakeel.core.evidence_models import Assertion, VerificationDetail, VerificationIssue


def preserve_unselected(
    assertions: tuple[Assertion, ...], touched_file_ids: set[str]
) -> tuple[ObservationDraft, ...]:
    """Keep all non-replaced source anchors, including completely untouched graph facts."""
    result: list[ObservationDraft] = []
    for assertion in assertions:
        if not assertion.predicate.startswith("kg."):
            continue
        anchors = tuple(
            anchor
            for anchor in assertion.anchors
            if anchor.asset_ref.asset_id not in touched_file_ids
        )
        if not anchors:
            continue
        detail = assertion.verification_detail
        if detail is not None and len(anchors) != len(assertion.anchors):
            locations = tuple(
                location
                for location in detail.locations
                if location.source.asset_id not in touched_file_ids
            )
            issues = tuple(
                dict.fromkeys(issue for location in locations for issue in location.issues)
            )
            if assertion.predicate == "kg.same_as":
                issues = (VerificationIssue(code="evidence"), *issues)
            if not locations:
                issues = (VerificationIssue(code="evidence"),)
            first = locations[0] if locations else None
            detail = VerificationDetail(
                issues=issues,
                locations=locations,
                evidence=first.evidence if first else None,
                head=first.head if first else None,
                tail=first.tail if first else None,
            )
        result.append(
            ObservationDraft(
                subject=assertion.subject,
                predicate=assertion.predicate,
                object=assertion.object,
                anchors=anchors,
                extractor=assertion.extractor,
                confidence=assertion.confidence,
                distance=assertion.distance,
                reason=assertion.reason,
                verification=("needs_review" if detail.issues else "verified")
                if detail
                else assertion.verification,
                verification_detail=detail,
            )
        )
    return tuple(result)
