# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Expose latest raw graph assertions and exact catalog associations for answers and review."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from datakeel.core.evidence_models import AssertionStatus
from datakeel.core.link_models import EntityLink, LinkContext, LinkGraph, LinkMetadata
from datakeel.core.models import AssetRef
from datakeel.storage.catalog_reads import read_snapshot
from datakeel.storage.database import Database
from datakeel.storage.evidence_decisions import assertion_view
from datakeel.storage.evidence_rows import AssertionRow
from datakeel.storage.link_context import read_link_graphs


def _links(session: Session, graphs: tuple[LinkGraph, ...]) -> tuple[EntityLink, ...]:
    entities = {entity.asset_ref.asset_id: entity for graph in graphs for entity in graph.entities}
    targets = {item.asset_ref.asset_id: item for item in read_snapshot(session).objects}
    result: list[EntityLink] = []
    rows = session.scalars(
        select(AssertionRow)
        .where(AssertionRow.predicate == "link.maps_to", AssertionRow.active.is_(True))
        .order_by(AssertionRow.id)
    )
    for row in rows:
        assertion = assertion_view(row)
        entity = entities.get(assertion.subject.asset_id)
        target = (
            targets.get(assertion.object.asset_id)
            if isinstance(assertion.object, AssetRef)
            else None
        )
        if (
            entity is None
            or target is None
            or assertion.subject.version != entity.asset_ref.version
        ):
            continue
        result.append(
            EntityLink(
                **LinkMetadata.model_validate_json(assertion.reason or "{}").model_dump(),
                assertion=assertion,
                entity=entity,
                target=target.model_copy(update={"asset_ref": assertion.object}),
            )
        )
    return tuple(result)


def read_link_context(db: Database) -> LinkContext:
    """Read current entities, raw relations and links; callers apply their review policy."""
    with db.session() as session:
        graphs = read_link_graphs(session)
        return LinkContext(
            entities=tuple(entity for graph in graphs for entity in graph.entities),
            assertions=tuple(assertion for graph in graphs for assertion in graph.assertions),
            links=_links(session, graphs),
        )


def list_links(
    db: Database, dataset_id: str | None = None, status: AssertionStatus | None = None
) -> tuple[EntityLink, ...]:
    """List reviewable latest associations with optional dataset and review-state filters."""
    with db.session() as session:
        graphs = tuple(
            graph for graph in read_link_graphs(session) if dataset_id in {None, graph.dataset_id}
        )
        return tuple(
            link for link in _links(session, graphs) if status in {None, link.assertion.status}
        )


def entity_links(db: Database, entity_id: str) -> tuple[EntityLink, ...]:
    """Read current associations for one graph entity, including its rejected decisions."""
    return tuple(link for link in list_links(db) if link.entity.asset_ref.asset_id == entity_id)
