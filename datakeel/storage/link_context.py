# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Read one published graph version per dataset without unsafe alias merging."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from datakeel.core.evidence_models import Assertion
from datakeel.core.kg_contracts import KGSchema
from datakeel.core.kg_execution import KGJob
from datakeel.core.kg_product import KGEntity
from datakeel.core.kg_registry import register_kg_schema
from datakeel.core.link_models import LinkGraph
from datakeel.core.models import LineageEvent
from datakeel.storage.database import EventRow, VersionRow
from datakeel.storage.evidence_decisions import assertion_view
from datakeel.storage.evidence_rows import AssertionRow
from datakeel.storage.kg_rows import KGRunRow


def _latest_events(session: Session) -> tuple[LineageEvent, ...]:
    events = tuple(
        sorted(
            (
                LineageEvent.model_validate(row.payload)
                for row in session.scalars(
                    select(EventRow).where(
                        EventRow.payload["operator"].as_string() == "evidence.kg"
                    )
                )
            ),
            key=lambda event: (event.occurred_at, event.event_id),
        )
    )
    version_ids = {str(event.params["kg_version_id"]) for event in events}
    versions = {
        row.id: row.created_at
        for row in session.scalars(select(VersionRow).where(VersionRow.id.in_(version_ids)))
    }
    first_seen: dict[tuple[str, str], float] = {}
    for event in events:
        key = (str(event.params["kg_dataset_id"]), str(event.params["kg_version_id"]))
        first_seen.setdefault(key, versions.get(key[1], event.occurred_at.timestamp()))
    latest = dict(sorted(first_seen, key=lambda key: first_seen[key]))
    return tuple(
        event
        for event in events
        if latest[str(event.params["kg_dataset_id"])] == str(event.params["kg_version_id"])
    )


def _graph_assertions(
    session: Session, entities: dict[str, KGEntity], version: str
) -> tuple[Assertion, ...]:
    return tuple(
        assertion_view(row)
        for row in session.scalars(
            select(AssertionRow)
            .where(
                AssertionRow.predicate.like("kg.%"),
                AssertionRow.predicate != "kg.same_as",
                AssertionRow.active.is_(True),
                AssertionRow.subject_id.in_(entities),
                AssertionRow.payload["subject"]["version"].as_string() == version,
            )
            .order_by(AssertionRow.id)
        )
    )


def read_link_graphs(session: Session) -> tuple[LinkGraph, ...]:
    """Resolve latest published versions and only active raw graph assertions."""
    events = _latest_events(session)
    for event in events:
        register_kg_schema(KGSchema.model_validate(event.params["kg_schema"]))
    graphs: list[LinkGraph] = []
    for dataset_id in sorted({str(event.params["kg_dataset_id"]) for event in events}):
        selected = tuple(event for event in events if event.params["kg_dataset_id"] == dataset_id)
        entities = {
            entity.asset_ref.asset_id: entity
            for event in selected
            for value in event.params.get("kg_entities", [])
            if (entity := KGEntity.model_validate(value))
        }
        version = str(selected[-1].params["kg_version_id"])
        current = _graph_assertions(session, entities, version)
        mentioned = {item.subject.asset_id for item in current if item.predicate == "kg.mentions"}
        runs = {str(event.params["run_id"]) for event in selected}
        graphs.append(
            LinkGraph(
                dataset_id=dataset_id,
                version_id=version,
                entities=tuple(
                    entity for key, entity in sorted(entities.items()) if key in mentioned
                ),
                assertions=current,
                documents=tuple(
                    document
                    for row in session.scalars(select(KGRunRow).where(KGRunRow.id.in_(runs)))
                    for document in KGJob.model_validate(row.payload).documents
                ),
            )
        )
    return tuple(graphs)
