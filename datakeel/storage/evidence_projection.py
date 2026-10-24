# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Rebuild disposable assertions and cache solely from immutable events and audits."""

import hashlib
import json
from graphlib import CycleError, TopologicalSorter

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from datakeel.core.errors import ValidationError
from datakeel.core.evidence_cache import EvidenceRebuildResult, KnowledgeBundle
from datakeel.core.evidence_models import AssertionDecision
from datakeel.core.models import LineageEvent
from datakeel.storage.database import Database
from datakeel.storage.events import all_events
from datakeel.storage.evidence_decisions import apply_decision, assertion_view
from datakeel.storage.evidence_rows import AssertionDecisionRow, AssertionRow, EvidenceCacheRow
from datakeel.storage.evidence_store import project_bundle, validated_bundle

PROJECTOR_VERSION = "1.1"
_CANONICAL_FIELDS = {
    "subject",
    "predicate",
    "object",
    "status",
    "anchors",
    "extractor",
    "producer_event_id",
    "verification",
    "verification_detail",
}


def normalized_hash(session: Session) -> str:
    """Hash the amendment's fixed canonical fields and projection schema version."""
    content = [
        assertion_view(row).model_dump(mode="json", include=_CANONICAL_FIELDS)
        for row in session.scalars(select(AssertionRow).order_by(AssertionRow.id))
    ]
    return hashlib.sha256(
        json.dumps(
            {"projector_version": PROJECTOR_VERSION, "assertions": content},
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
    ).hexdigest()


def projection_hash(db: Database) -> str:
    """Return the stable comparison identity of the current evidence projection."""
    with db.session() as session:
        return normalized_hash(session)


def rebuild_evidence(db: Database, expected_hash: str | None = None) -> EvidenceRebuildResult:
    """Atomically reconstruct observations and reapply immutable decision history."""
    with db.session() as session:
        db.lock_writes(session)
        before = expected_hash or normalized_hash(session)
        bundles = ordered_bundles(all_events(session))
        session.execute(delete(EvidenceCacheRow))
        session.execute(delete(AssertionRow))
        for event, bundle in bundles:
            project_bundle(session, event, bundle)
        session.flush()
        for row in session.scalars(
            select(AssertionDecisionRow).order_by(AssertionDecisionRow.sequence)
        ):
            apply_decision(session, AssertionDecision.model_validate(row.payload))
        session.flush()
        after = normalized_hash(session)
        result = EvidenceRebuildResult(
            before_hash=before,
            after_hash=after,
            matches=before == after,
            assertions=sum(len(bundle.assertions) for _, bundle in bundles),
            events=len(bundles),
        )
        session.commit()
        return result


def ordered_bundles(events: list[LineageEvent]) -> list[tuple[LineageEvent, KnowledgeBundle]]:
    """Replay cache predecessors first even when event timestamps are identical."""
    bundles = {
        event.event_id: (event, validated_bundle(event))
        for event in sorted(events, key=lambda event: (event.occurred_at, event.event_id))
        if "knowledge_bundle" in event.params
    }
    dependencies = {key: bundle.prior_cache_event_ids for key, (_, bundle) in bundles.items()}
    if any(parent not in bundles for parents in dependencies.values() for parent in parents):
        msg = "Knowledge bundle cache predecessor event is missing"
        raise ValidationError(msg)
    try:
        return [bundles[key] for key in TopologicalSorter(dependencies).static_order()]
    except CycleError as exc:
        msg = "Knowledge bundle cache predecessors contain a cycle"
        raise ValidationError(msg) from exc
