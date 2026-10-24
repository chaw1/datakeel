# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Carry human decisions across evidence identities without rewriting extracted facts."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from datakeel.core.evidence_models import Assertion, AssertionDecision
from datakeel.core.models import LineageEvent
from datakeel.storage.evidence_decisions import append_decision, assertion_view
from datakeel.storage.evidence_rows import AssertionDecisionRow, AssertionRow


def _review_key(assertion: Assertion) -> tuple[str, str, str]:
    return (
        assertion.subject.model_dump_json(exclude={"display_name"}),
        assertion.predicate,
        ""
        if assertion.predicate == "kg.mentions"
        else assertion.object.model_dump_json(exclude={"display_name"}),
    )


def _latest_reviews(
    session: Session, assertions: tuple[Assertion, ...]
) -> dict[tuple[str, str, str], AssertionDecision]:
    statement = (
        select(AssertionRow, AssertionDecisionRow)
        .join(AssertionDecisionRow, AssertionRow.id == AssertionDecisionRow.assertion_id)
        .where(
            AssertionRow.subject_id.in_({item.subject.asset_id for item in assertions}),
            AssertionRow.predicate.like("kg.%"),
        )
        .order_by(AssertionDecisionRow.sequence)
    )
    reviews: dict[tuple[str, str, str], AssertionDecision] = {}
    for row, decision_row in session.execute(statement):
        decision = AssertionDecision.model_validate(decision_row.payload)
        if decision.producer_event_id is None and decision.action in {
            "accept",
            "reject",
            "restore",
        }:
            reviews[_review_key(assertion_view(row))] = decision
    return reviews


def inherit_reviews(session: Session, event: LineageEvent, identifiers: set[str]) -> None:
    """Apply the latest direct review for each versioned triple or entity mention.

    Extraction identities still bind configuration and source positions. Inheritance
    records point to the original human decision and never become new human authority.
    A later explicit restore also supersedes older accepted or rejected decisions.
    """
    assertions = tuple(
        assertion_view(row)
        for row in session.scalars(select(AssertionRow).where(AssertionRow.id.in_(identifiers)))
    )
    reviews = _latest_reviews(session, assertions)
    for assertion in assertions:
        review = reviews.get(_review_key(assertion))
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
                    "human_review_inherited_for_same_versioned_entity_or_triple; "
                    f"source_assertion_id={review.assertion_id}; "
                    f"source_decision_id={review.id}"
                ),
                producer_event_id=event.event_id,
                occurred_at=event.occurred_at,
            ),
            f"kg-inherit-review:{event.event_id}:{assertion.id}",
        )
