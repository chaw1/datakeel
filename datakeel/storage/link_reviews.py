# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Preserve direct link reviews across entity and catalog revision changes."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from datakeel.core.evidence_models import Assertion, AssertionDecision
from datakeel.core.models import AssetRef, BoundaryModel, LineageEvent
from datakeel.storage.evidence_decisions import append_decision, assertion_view
from datakeel.storage.evidence_rows import AssertionDecisionRow, AssertionRow


class LinkReview(BoundaryModel):
    """Pair the latest human decision with its original immutable association."""

    assertion: Assertion
    decision: AssertionDecision


def review_key(assertion: Assertion) -> tuple[str, str, str]:
    """Intentionally omit both versions from the cross-version human-review identity."""
    return (
        assertion.subject.asset_id,
        assertion.predicate,
        assertion.object.asset_id if isinstance(assertion.object, AssetRef) else "",
    )


def latest_link_reviews(session: Session) -> tuple[LinkReview, ...]:
    """Read only direct human authority, ignoring inherited and invalidation decisions."""
    statement = (
        select(AssertionRow, AssertionDecisionRow)
        .join(AssertionDecisionRow, AssertionRow.id == AssertionDecisionRow.assertion_id)
        .where(AssertionRow.predicate == "link.maps_to")
        .order_by(AssertionDecisionRow.sequence)
    )
    reviews: dict[tuple[str, str, str], LinkReview] = {}
    for row, decision_row in session.execute(statement):
        decision = AssertionDecision.model_validate(decision_row.payload)
        if decision.producer_event_id is None and decision.action in {
            "accept",
            "reject",
            "restore",
        }:
            assertion = assertion_view(row)
            reviews[review_key(assertion)] = LinkReview(assertion=assertion, decision=decision)
    return tuple(reviews[key] for key in sorted(reviews))


def inherit_link_reviews(session: Session, event: LineageEvent, identifiers: set[str]) -> None:
    """Audit inherited link decisions without changing P8's version-scoped review policy."""
    reviews = {review_key(item.assertion): item.decision for item in latest_link_reviews(session)}
    for row in session.scalars(select(AssertionRow).where(AssertionRow.id.in_(identifiers))):
        assertion = assertion_view(row)
        review = reviews.get(review_key(assertion))
        if review is None or assertion.status == review.status:
            continue
        append_decision(
            session,
            AssertionDecision(
                assertion_id=assertion.id,
                action=review.action,
                previous_status=assertion.status,
                status=review.status,
                actor=review.actor,
                reason=(
                    "human_link_review_inherited_across_versions; "
                    f"source_assertion_id={review.assertion_id}; source_decision_id={review.id}"
                ),
                producer_event_id=event.event_id,
                occurred_at=event.occurred_at,
            ),
            f"link-inherit:{event.event_id}:{assertion.id}",
        )
