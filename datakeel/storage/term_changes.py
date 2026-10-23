# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Append-only glossary changes using authoritative catalog revisions."""

from sqlalchemy.orm import Session

from datakeel.core.catalog_models import CatalogObject
from datakeel.core.catalog_projection import snapshot_events
from datakeel.core.errors import ConflictError, NotFoundError, ValidationError
from datakeel.core.metric_models import TermDefinition
from datakeel.metrics.projection import build_snapshot, semantic_layer
from datakeel.storage.catalog_store import publish_snapshot_in_session, read_snapshot
from datakeel.storage.events import all_events


def current_term(session: Session, term: str) -> CatalogObject:
    """Read the exact current glossary revision inside an action transaction."""
    for item in read_snapshot(session).objects:
        if item.asset_ref.asset_type == "term" and item.asset_ref.asset_id == f"term/{term}":
            return item
    msg = f"Term not found: {term}"
    raise NotFoundError(msg)


def change_term(
    session: Session, definition: TermDefinition, expected_revision: int, actor: str
) -> CatalogObject:
    """Replace one existing term after checking its catalog version expectation."""
    before = current_term(session, definition.term)
    if before.revision != expected_revision:
        msg = f"Expected term revision {expected_revision}; current is {before.revision}"
        raise ConflictError(msg)
    catalog = read_snapshot(session)
    if not any(
        item.asset_ref.asset_type == definition.means.kind
        and item.asset_ref.asset_id == definition.means.id
        for item in catalog.objects
    ):
        msg = f"Term target is not registered: {definition.means.kind}/{definition.means.id}"
        raise ValidationError(msg)
    layer = semantic_layer(catalog)
    layer = layer.model_copy(
        update={
            "terms": [definition if item.term == definition.term else item for item in layer.terms]
        }
    )
    publish_snapshot_in_session(session, build_snapshot(layer, catalog), "TERM_CHANGE", actor)
    return current_term(session, definition.term)


def historical_term(session: Session, term: str, revision: int) -> TermDefinition:
    """Recover a prior definition while leaving every source event immutable."""
    for _, snapshot in snapshot_events(all_events(session)):
        for item in snapshot.objects:
            if item.asset_ref.asset_id == f"term/{term}" and item.revision == revision:
                return TermDefinition.model_validate(item.properties.root)
    msg = f"Term revision not found: {term}@{revision}"
    raise NotFoundError(msg)
