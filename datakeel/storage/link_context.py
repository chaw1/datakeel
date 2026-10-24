# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Read one published graph version per dataset without unsafe alias merging."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from datakeel.core.kg_contracts import KGSchema
from datakeel.core.kg_execution import KGJob
from datakeel.core.kg_product import KGEntity
from datakeel.core.kg_registry import register_kg_schema
from datakeel.core.link_models import LinkGraph
from datakeel.core.models import LineageEvent
from datakeel.storage.database import VersionRow
from datakeel.storage.events import all_events
from datakeel.storage.evidence_store import read_assertions
from datakeel.storage.kg_rows import KGRunRow


def _latest_events(session: Session) -> tuple[LineageEvent, ...]:
    events = tuple(
        sorted(
            (event for event in all_events(session) if event.operator == "evidence.kg"),
            key=lambda event: (event.occurred_at, event.event_id),
        )
    )
    versions = {row.id: row.created_at for row in session.scalars(select(VersionRow))}
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


def read_link_graphs(session: Session) -> tuple[LinkGraph, ...]:
    """Resolve latest published versions and only active raw graph assertions."""
    events = _latest_events(session)
    for event in events:
        register_kg_schema(KGSchema.model_validate(event.params["kg_schema"]))
    assertions = tuple(
        item
        for item in read_assertions(session)
        if item.predicate.startswith("kg.") and item.predicate != "kg.same_as"
    )
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
        current = tuple(
            item
            for item in assertions
            if item.subject.asset_id in entities and item.subject.version == version
        )
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
