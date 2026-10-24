# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Derive prior graph provenance from immutable bundle input references."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from datakeel.core.evidence_models import Assertion
from datakeel.core.models import AssetRef, LineageEvent
from datakeel.storage.database import EventRow


def prior_bundle_inputs(session: Session, assertions: tuple[Assertion, ...]) -> list[AssetRef]:
    """Link carried and replaced graph observations back to their original event artifacts."""
    parents = {assertion.producer_event_id for assertion in assertions}
    return [
        ref
        for row in session.scalars(select(EventRow).where(EventRow.event_id.in_(parents)))
        for ref in LineageEvent.model_validate(row.payload).outputs
        if ref.asset_type == "knowledge_bundle"
    ]


def kg_predecessors(session: Session, event: LineageEvent) -> tuple[str, ...]:
    """Resolve existing artifact inputs to event identities without trusting supplied ids."""
    if event.operator != "evidence.kg":
        return ()
    references = {
        ref.model_dump_json() for ref in event.inputs if ref.asset_type == "knowledge_bundle"
    }
    return tuple(
        sorted(
            prior.event_id
            for row in session.scalars(select(EventRow))
            if (prior := LineageEvent.model_validate(row.payload)).operator == "evidence.kg"
            and references.intersection(ref.model_dump_json() for ref in prior.outputs)
        )
    )
