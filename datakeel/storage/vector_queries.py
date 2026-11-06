# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Side-effect-free vector reads with whole-run authorization and snapshot-bound pages."""

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from datakeel.core.data_asset_models import AccessContext
from datakeel.core.evidence_models import Assertion
from datakeel.core.models import AssetRef, BoundaryModel, LineageEvent
from datakeel.core.vector_assertion_rules import assertion_references
from datakeel.core.vector_measurements import CoverageMeasurement
from datakeel.core.vector_models import vector_hash
from datakeel.core.vector_query import (
    VECTOR_PREDICATES,
    VectorQuery,
    VectorQueryEvent,
    VectorQueryResult,
)
from datakeel.core.vector_results import VectorTaskReport
from datakeel.storage.data_asset_access import require_access_in_session
from datakeel.storage.database import Database
from datakeel.storage.evidence_decisions import assertion_view
from datakeel.storage.evidence_rows import AssertionRow
from datakeel.storage.vector_current import vector_assertion_current
from datakeel.storage.vector_cursor import cursor_offset, encode_cursor
from datakeel.storage.vector_query_snapshot import (
    publication_current,
    query_events,
    query_report,
    query_sources,
    query_task,
    reference_digest,
    reference_states,
)


def _matches(item: Assertion, query: VectorQuery) -> bool:
    measurement = item.measurement
    return (
        item.predicate == VECTOR_PREDICATES[query.kind]
        and item.status in query.statuses
        and (not query.subject_ids or item.subject.asset_id in query.subject_ids)
        and (
            query.cluster_id is None
            or (
                isinstance(item.object, AssetRef)
                and item.object.asset_type == "semantic_cluster"
                and item.object.asset_id == query.cluster_id
            )
        )
        and (
            query.reference_id is None
            or (
                isinstance(measurement, CoverageMeasurement)
                and any(m.subject.asset_id == query.reference_id for m in measurement.references)
            )
        )
    )


def query_vectors(db: Database, query: VectorQuery, access: AccessContext) -> VectorQueryResult:
    """Authorize the entire run before filtering; never hide denial as an empty page."""
    with db.session() as session:
        if db.sqlite:
            session.execute(text("BEGIN"))
        else:
            session.connection(execution_options={"isolation_level": "REPEATABLE READ"})
        return _query(session, db, query, access)


class _Snapshot(BoundaryModel):
    facts: tuple[Assertion, ...]
    current: tuple[bool, ...]
    references_current: tuple[bool, ...]
    events: tuple[LineageEvent, ...]
    report: VectorTaskReport
    reference_digest: str

    def digest(self) -> str:
        return vector_hash(self.model_dump(mode="json"))


def _read(session: Session, query: VectorQuery, access: AccessContext) -> _Snapshot:
    task = query_task(session, query.run_id, query.dataset_id)
    events = query_events(session, query.run_id)
    rows = list(
        session.scalars(
            select(AssertionRow)
            .where(
                AssertionRow.payload["run_id"].as_string() == query.run_id,
                AssertionRow.predicate.in_(tuple(VECTOR_PREDICATES.values())),
            )
            .order_by(AssertionRow.id)
        )
    )
    facts = tuple(assertion_view(row) for row in rows)
    refs = (
        *query_sources(session, task),
        *(r for e in events for r in e.inputs),
        *(r for fact in facts for r in assertion_references(fact)),
    )
    require_access_in_session(session, tuple(dict.fromkeys(refs)), access, record=False)
    current = tuple(
        row.active and vector_assertion_current(session, fact)
        for row, fact in zip(rows, facts, strict=True)
    )
    return _Snapshot(
        facts=facts,
        current=current,
        events=events,
        references_current=(
            *reference_states(session, events),
            *publication_current(session, events),
        ),
        reference_digest=reference_digest(events),
        report=query_report(session, task, events),
    )


def _public_events(events: tuple[LineageEvent, ...]) -> tuple[VectorQueryEvent, ...]:
    return tuple(
        VectorQueryEvent(
            event_id=e.event_id,
            operator=str(e.operator),
            mode=str(e.params.get("mode", "fake")),
            implementation=str(e.params.get("fake_version", "we-e2-fake-v1")),
            contract=str(e.params.get("contract", "we-e1-v1")),
            inputs=tuple(e.inputs),
        )
        for e in events
    )


def _operator(query: VectorQuery) -> str:
    return {
        "duplicate": "evidence.semantic_duplicate",
        "cluster": "evidence.semantic_cluster",
        "outlier": "evidence.semantic_outlier",
        "coverage": "evidence.coverage_gap",
    }[query.kind]


def _query(
    session: Session, db: Database, query: VectorQuery, access: AccessContext
) -> VectorQueryResult:
    state = _read(session, query, access)
    snapshot = state.digest()
    binding = vector_hash(
        [
            snapshot,
            query.model_dump(mode="json", exclude={"cursor"}),
            access.model_dump(mode="json"),
            str(db.engine.url),
        ]
    )
    items = (
        tuple(
            f
            for f, live in zip(state.facts, state.current, strict=True)
            if live and _matches(f, query)
        )
        if all(state.references_current)
        else ()
    )
    offset = cursor_offset(query.cursor, binding, len(items))
    page = items[offset : offset + query.page_size]
    status = (
        "stale"
        if not all((*state.current, *state.references_current))
        else "unpublished"
        if not any(
            e.operator == _operator(query) and "knowledge_bundle" in e.params for e in state.events
        )
        else "current"
    )
    return VectorQueryResult(
        run_id=query.run_id,
        kind=query.kind,
        snapshot=snapshot,
        reference_digest=state.reference_digest,
        status=status,
        reason="vector_results_stale"
        if status == "stale"
        else "vector_results_unpublished"
        if status == "unpublished"
        else None,
        items=page,
        total=len(items),
        report=state.report,
        events=_public_events(state.events),
        next_cursor=encode_cursor(binding, offset + len(page))
        if offset + len(page) < len(items)
        else None,
    )
