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
from datakeel.core.evidence_replay import EVIDENCE_PROJECTOR, EvidenceWatermark
from datakeel.core.models import LineageEvent
from datakeel.core.vector_models import VECTOR_OPERATORS, require_local_vector_objects, vector_hash
from datakeel.dataset_store.events import all_events
from datakeel.storage.database import Database
from datakeel.storage.evidence_decisions import apply_decision, assertion_view
from datakeel.storage.evidence_rows import AssertionDecisionRow, AssertionRow, EvidenceCacheRow
from datakeel.storage.evidence_store import project_bundle, validated_bundle
from datakeel.storage.vector_cache import lock_evidence
from datakeel.storage.vector_rows import VectorCacheRow

PROJECTOR_VERSION = EVIDENCE_PROJECTOR.version
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
    legacy: list[dict[str, object]] = []
    vectors: list[dict[str, object]] = []
    for row in session.scalars(select(AssertionRow).order_by(AssertionRow.id)):
        value = assertion_view(row)
        if value.predicate in {
            "semantic_duplicate_of",
            "semantic_cluster_member",
            "semantic_outlier",
            "coverage_gap",
        }:
            fields = (_CANONICAL_FIELDS - {"producer_event_id"}) | {
                "measurement",
                "reason",
                "distance",
            }
            vectors.append({**value.model_dump(mode="json", include=fields), "active": row.active})
        else:
            legacy.append(value.model_dump(mode="json", include=_CANONICAL_FIELDS))
    vectors.sort(key=lambda item: json.dumps(item, sort_keys=True))
    content: dict[str, object] = {
        "projector_version": PROJECTOR_VERSION,
        "assertions": legacy + vectors,
    }
    vector_facts = _vector_facts(session)
    if vector_facts:
        content["vector_bundles"] = vector_facts
        content["vector_decisions"] = _vector_decisions(session)
    return hashlib.sha256(
        json.dumps(content, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def projection_hash(db: Database) -> str:
    """Return the stable comparison identity of the current evidence projection."""
    with db.session() as session:
        return normalized_hash(session)


def rebuild_evidence(db: Database, expected_hash: str | None = None) -> EvidenceRebuildResult:
    """Atomically reconstruct observations and reapply immutable decision history."""
    with db.session() as session:
        db.lock_writes(session)
        lock_evidence(session)
        before = expected_hash or normalized_hash(session)
        source_watermark = evidence_watermark(session)
        events = all_events(session)
        if any(event.operator in VECTOR_OPERATORS for event in events):
            require_local_vector_objects()
        bundles = ordered_bundles(events)
        session.execute(delete(EvidenceCacheRow))
        session.execute(delete(VectorCacheRow))
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
        if evidence_watermark(session) != source_watermark:
            msg = "Evidence fact sources changed during rebuild"
            raise ValidationError(msg)
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


def evidence_watermark(session: Session) -> EvidenceWatermark:
    """Expose a composite source watermark for independent diff and rebuild verification."""
    events = sorted(
        (event.event_id, vector_hash(event.model_dump(mode="json")))
        for event in all_events(session)
        if "knowledge_bundle" in event.params
    )
    decisions = [
        row.payload
        for row in session.scalars(
            select(AssertionDecisionRow).order_by(AssertionDecisionRow.sequence)
        )
    ]
    return EvidenceWatermark(bundles=vector_hash(events), decisions=vector_hash(decisions))


def _vector_facts(session: Session) -> list[dict[str, object]]:
    sources: list[dict[str, object]] = []
    for event in all_events(session):
        if event.operator not in VECTOR_OPERATORS or "knowledge_bundle" not in event.params:
            continue
        require_local_vector_objects()
        bundle = validated_bundle(event)
        sources.append(
            {
                "operator": event.operator,
                "parameters": event.params.get("parameters"),
                "samples": [s.model_dump(mode="json") for s in bundle.vector_samples],
                "pairs": [p.model_dump(mode="json") for p in bundle.vector_pairs],
                "findings": [f.model_dump(mode="json") for f in bundle.vector_findings],
                "scope": bundle.vector_scope.model_dump(mode="json")
                if bundle.vector_scope
                else None,
                "report": event.quality.get("vector"),
            }
        )
    return sorted(sources, key=lambda item: json.dumps(item, sort_keys=True))


def _vector_decisions(session: Session) -> list[dict[str, object]]:
    decisions: list[dict[str, object]] = []
    for row in session.scalars(
        select(AssertionDecisionRow).order_by(AssertionDecisionRow.sequence)
    ):
        assertion = session.get(AssertionRow, row.assertion_id)
        if assertion is None or assertion.predicate not in {
            "semantic_duplicate_of",
            "semantic_cluster_member",
            "semantic_outlier",
            "coverage_gap",
        }:
            continue
        content = {
            key: value
            for key, value in assertion.payload.items()
            if key
            not in {
                "id",
                "created_at",
                "run_id",
                "producer_event_id",
                "decided_at",
                "decided_by",
                "status",
            }
        }
        decisions.append(
            {
                "assertion": vector_hash(content),
                **{
                    key: value
                    for key, value in row.payload.items()
                    if key not in {"id", "occurred_at", "producer_event_id", "assertion_id"}
                },
            }
        )
    return decisions
