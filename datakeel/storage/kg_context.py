# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Recover graph vocabulary and entity projections from authoritative extraction events."""

from datakeel.core.evidence_models import Assertion
from datakeel.core.kg_contracts import KGSchema
from datakeel.core.kg_product import KGEntity
from datakeel.core.kg_queries import KGQuery
from datakeel.core.kg_registry import register_kg_schema
from datakeel.core.models import BoundaryModel, LineageEvent
from datakeel.storage.database import Database
from datakeel.storage.events import all_events
from datakeel.storage.evidence_store import read_assertions


class KGContext(BoundaryModel):
    """Keep one graph version and its existing evidence projection together."""

    dataset_id: str | None = None
    version_id: str | None = None
    entities: tuple[KGEntity, ...] = ()
    assertions: tuple[Assertion, ...] = ()
    events: tuple[LineageEvent, ...] = ()


def graph_events(db: Database) -> tuple[LineageEvent, ...]:
    """Register event-frozen vocabularies before parsing custom assertion predicates."""
    with db.session() as session:
        events = tuple(
            sorted(
                (event for event in all_events(session) if "kg_schema" in event.params),
                key=lambda event: (event.occurred_at, event.event_id),
            )
        )
    for event in events:
        register_kg_schema(KGSchema.model_validate(event.params["kg_schema"]))
    return events


def read_context(db: Database, query: KGQuery, *, include_invalidated: bool = False) -> KGContext:
    """Resolve an explicit or latest dataset version without mixing graph scopes."""
    events = tuple(
        event
        for event in graph_events(db)
        if (query.dataset_id is None or event.params.get("kg_dataset_id") == query.dataset_id)
        and (query.version_id is None or event.params.get("kg_version_id") == query.version_id)
    )
    if not events:
        return KGContext(dataset_id=query.dataset_id, version_id=query.version_id)
    dataset_id = str(events[-1].params["kg_dataset_id"])
    version_id = str(events[-1].params["kg_version_id"])
    selected = tuple(
        event
        for event in events
        if event.params.get("kg_dataset_id") == dataset_id
        and event.params.get("kg_version_id") == version_id
    )
    entities = {
        entity.asset_ref.asset_id: entity
        for event in selected
        for value in event.params.get("kg_entities", [])
        if (entity := KGEntity.model_validate(value)).asset_ref.version == version_id
    }
    with db.session() as session:
        assertions = tuple(
            assertion
            for assertion in read_assertions(session, include_invalidated=include_invalidated)
            if assertion.subject.asset_id in entities
            and assertion.subject.version == version_id
            and assertion.predicate.startswith("kg.")
        )
    mentioned = {item.subject.asset_id for item in assertions if item.predicate == "kg.mentions"}
    return KGContext(
        dataset_id=dataset_id,
        version_id=version_id,
        entities=tuple(entity for key, entity in entities.items() if key in mentioned),
        assertions=assertions,
        events=selected,
    )
