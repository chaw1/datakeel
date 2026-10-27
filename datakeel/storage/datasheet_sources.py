# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Version-scoped lineage, evidence review and knowledge-graph documentation facts."""

from collections import Counter

from sqlalchemy import select
from sqlalchemy.orm import Session

from datakeel.core.datasheet_models import DatasheetFact
from datakeel.core.evidence_models import AssertionDecision
from datakeel.core.kg_product import KGEntity
from datakeel.core.models import LineageEvent, utcnow
from datakeel.storage.database import VersionRow
from datakeel.storage.datasheet_values import make_fact
from datakeel.storage.events import all_events
from datakeel.storage.evidence_rows import AssertionDecisionRow, AssertionRow


def _scoped_events(
    session: Session, dataset_id: str, version: VersionRow
) -> tuple[LineageEvent, ...]:
    file_ids = {str(item["id"]) for item in version.manifest}
    return tuple(
        sorted(
            (
                event
                for event in all_events(session)
                if (version.task_id is not None and event.source_ref == version.task_id)
                or (
                    event.params.get("kg_dataset_id") == dataset_id
                    and event.params.get("kg_version_id") == version.id
                )
                or any(
                    ref.asset_id == version.id
                    or (ref.version == version.id and ref.asset_id in file_ids | {dataset_id})
                    for ref in (*event.inputs, *event.outputs)
                )
            ),
            key=lambda event: (event.occurred_at, event.event_id),
        )
    )


def _lineage_facts(events: tuple[LineageEvent, ...]) -> tuple[DatasheetFact, ...]:
    result: list[DatasheetFact] = []
    for event in events:
        chapter = "collection" if event.event_type == "IMPORT" else "preprocessing"
        for field, value in (
            ("lineage.operator", event.operator),
            ("lineage.run_state", event.run_state),
            ("lineage.occurred_at", event.occurred_at.isoformat()),
        ):
            fact = make_fact(
                chapter, "lineage_event", event.event_id, field, value, event.occurred_at
            )
            if fact is not None:
                result.append(fact)
    return tuple(result)


def _version_assertions(
    session: Session, version: VersionRow, events: tuple[LineageEvent, ...]
) -> tuple[AssertionRow, ...]:
    event_ids = {event.event_id for event in events}
    return tuple(
        row
        for row in session.scalars(select(AssertionRow).order_by(AssertionRow.id))
        if row.producer_event_id in event_ids
        and (
            row.payload.get("subject", {}).get("version") == version.id
            or any(
                anchor.get("asset_ref", {}).get("version") == version.id
                for anchor in row.payload.get("anchors", [])
            )
        )
    )


def _assertion_facts(
    version: VersionRow, assertions: tuple[AssertionRow, ...]
) -> tuple[DatasheetFact, ...]:
    if not assertions:
        return ()
    active = tuple(row for row in assertions if row.active)
    measured_at = utcnow()
    values: tuple[tuple[str, object], ...] = (
        ("assertions.count", len(active)),
        ("assertions.status_counts", dict(sorted(Counter(row.status for row in active).items()))),
        (
            "assertions.verification_counts",
            dict(sorted(Counter(row.verification or "unrecorded" for row in active).items())),
        ),
        (
            "assertions.predicate_counts",
            dict(sorted(Counter(row.predicate for row in active).items())),
        ),
        ("assertions.inactive_count", len(assertions) - len(active)),
    )
    return tuple(
        fact
        for field, value in values
        if (
            fact := make_fact(
                "preprocessing", "version_assertions", version.id, field, value, measured_at
            )
        )
        is not None
    )


def _decision_facts(
    session: Session, assertions: tuple[AssertionRow, ...]
) -> tuple[DatasheetFact, ...]:
    identifiers = {row.id for row in assertions}
    if not identifiers:
        return ()
    result: list[DatasheetFact] = []
    for row in session.scalars(
        select(AssertionDecisionRow)
        .where(AssertionDecisionRow.assertion_id.in_(identifiers))
        .order_by(AssertionDecisionRow.sequence)
    ):
        decision = AssertionDecision.model_validate(row.payload)
        fact = make_fact(
            "preprocessing",
            "assertion_decision",
            row.id,
            "decisions.review",
            {
                "assertion_id": row.assertion_id,
                "action": decision.action,
                "status": decision.status,
                "actor": decision.actor,
                "reason": decision.reason,
            },
            decision.occurred_at,
        )
        if fact is not None:
            result.append(fact)
    return tuple(result)


def _graph_facts(
    version: VersionRow, events: tuple[LineageEvent, ...], assertions: tuple[AssertionRow, ...]
) -> tuple[DatasheetFact, ...]:
    graph_events = tuple(event for event in events if "kg_entities" in event.params)
    if not graph_events:
        return ()
    mentioned = {
        row.subject_id for row in assertions if row.active and row.predicate == "kg.mentions"
    }
    entities = {
        entity.asset_ref.asset_id: {"name": entity.name, "type": entity.type}
        for event in graph_events
        for value in event.params["kg_entities"]
        if (entity := KGEntity.model_validate(value)).asset_ref.version == version.id
        and entity.asset_ref.asset_id in mentioned
    }
    measured_at = max(event.occurred_at for event in graph_events)
    candidates = (
        make_fact(
            "composition",
            "version_graph",
            version.id,
            "kg.entities",
            [entities[key] for key in sorted(entities)],
            measured_at,
        ),
        make_fact(
            "composition",
            "version_graph",
            version.id,
            "kg.relation_count",
            sum(
                row.active and row.predicate.startswith("kg.") and row.predicate != "kg.mentions"
                for row in assertions
            ),
            measured_at,
        ),
    )
    return tuple(fact for fact in candidates if fact is not None)


def source_facts(
    session: Session, dataset_id: str, version: VersionRow
) -> tuple[DatasheetFact, ...]:
    """Extract only events and reviewed assertions belonging to one exact version."""
    events = _scoped_events(session, dataset_id, version)
    assertions = _version_assertions(session, version, events)
    return (
        *_lineage_facts(events),
        *_assertion_facts(version, assertions),
        *_decision_facts(session, assertions),
        *_graph_facts(version, events, assertions),
    )
