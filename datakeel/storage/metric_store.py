# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Event-backed semantic installation, historical reads, and reversible revisions."""

from sqlalchemy.orm import Session

from datakeel.core.catalog_models import ImportReport
from datakeel.core.catalog_projection import snapshot_events
from datakeel.core.errors import ConflictError, NotFoundError, ValidationError
from datakeel.core.metric_history_models import MetricHistory
from datakeel.core.metric_models import MetricCard, MetricDefinition, MetricMutation, SemanticLayer
from datakeel.metrics.projection import (
    SEMANTIC_SCOPE,
    build_snapshot,
    metric_cards,
    resolved_metric_cards,
    semantic_layer,
)
from datakeel.storage.catalog_store import (
    lock_catalog,
    publish_snapshot_in_session,
    read_snapshot,
)
from datakeel.storage.database import Database
from datakeel.storage.events import all_events
from datakeel.storage.metric_audit import audit_in_session


def install_layer(db: Database, layer: SemanticLayer, actor: str = "local-user") -> ImportReport:
    """Validate YAML expected versions and install semantic changes as new revisions."""
    with db.session() as session:
        db.lock_writes(session)
        lock_catalog(session)
        catalog = read_snapshot(session)
        existing = {item.definition.id: item.definition for item in metric_cards(catalog)}
        metrics = [_import_revision(item, existing.get(item.id)) for item in layer.metrics]
        snapshot = build_snapshot(layer.model_copy(update={"metrics": metrics}), catalog)
        result = publish_snapshot_in_session(session, snapshot, "METRIC_CHANGE", actor)
        session.commit()
        return result


def list_metrics(db: Database) -> list[MetricCard]:
    """Return current metric cards from the authoritative event projection."""
    with db.session() as session:
        return resolved_metric_cards(read_snapshot(session))


def read_layer(db: Database) -> SemanticLayer:
    """Return current metric, dimension, and glossary definitions together."""
    with db.session() as session:
        return semantic_layer(read_snapshot(session))


def get_metric(db: Database, metric_id: str) -> MetricCard:
    """Read one metric by its stable semantic identity."""
    with db.session() as session:
        return metric_in_session(session, metric_id)


def metric_in_session(session: Session, metric_id: str) -> MetricCard:
    """Read a current metric inside an existing action transaction."""
    for card in resolved_metric_cards(read_snapshot(session)):
        if card.definition.id == metric_id:
            return card
    msg = f"Metric not found: {metric_id}"
    raise NotFoundError(msg)


def metric_history(db: Database, metric_id: str) -> list[MetricCard]:
    """Replay unique revisions of one metric from append-only semantic events."""
    with db.session() as session:
        return history_in_session(session, metric_id)


def metric_history_detail(db: Database, metric_id: str) -> MetricHistory:
    """Expose semantic revisions and controlled version transitions together."""
    with db.session() as session:
        metric_in_session(session, metric_id)
        return MetricHistory(
            metric_id=metric_id,
            versions=tuple(history_in_session(session, metric_id)),
            audit=audit_in_session(session, metric_id),
        )


def history_in_session(session: Session, metric_id: str) -> list[MetricCard]:
    """Read historical definitions without opening a second transaction."""
    versions: dict[int, MetricCard] = {}
    for _event, snapshot in snapshot_events(all_events(session)):
        if snapshot.scope == SEMANTIC_SCOPE:
            for card in metric_cards(snapshot):
                if card.definition.id == metric_id:
                    versions[card.definition.version] = card
    return [versions[version] for version in sorted(versions)]


def validate_metric_update(session: Session, definition: MetricDefinition) -> None:
    """Reject unresolved controlled changes while preserving permissive semantic imports."""
    lock_catalog(session)
    catalog = read_snapshot(session)
    layer = semantic_layer(catalog).model_copy(update={"metrics": [definition]})
    card = metric_cards(build_snapshot(layer, catalog))[0]
    if card.reasons:
        details = "\n".join(f"- {reason}" for reason in card.reasons)
        msg = f"Metric {definition.id} has unresolved catalog references:\n{details}"
        raise ValidationError(msg)


def update_metric_in_session(
    session: Session, definition: MetricDefinition, actor: str = "local-user"
) -> MetricMutation:
    """Append a new semantic version within a controlled action transaction."""
    lock_catalog(session)
    before = metric_in_session(session, definition.id)
    if definition.version != before.definition.version:
        msg = (
            f"Expected metric version {definition.version}; current is {before.definition.version}"
        )
        raise ConflictError(msg)
    definition = definition.model_copy(update={"version": before.definition.version + 1})
    catalog = read_snapshot(session)
    layer = semantic_layer(catalog)
    layer = layer.model_copy(
        update={
            "metrics": [definition if item.id == definition.id else item for item in layer.metrics]
        }
    )
    snapshot = build_snapshot(layer, catalog)
    report = publish_snapshot_in_session(session, snapshot, "METRIC_CHANGE", actor)
    after = next(item for item in metric_cards(snapshot) if item.definition.id == definition.id)
    return MetricMutation(before=before, after=after, event_id=report.event_id or "")


def rollback_metric_in_session(
    session: Session, metric_id: str, version: int, actor: str = "local-user"
) -> MetricMutation:
    """Restore prior semantics as a new revision, retaining every intermediate version."""
    lock_catalog(session)
    for card in history_in_session(session, metric_id):
        if card.definition.version == version:
            current = metric_in_session(session, metric_id)
            definition = card.definition.model_copy(update={"version": current.definition.version})
            return update_metric_in_session(session, definition, actor)
    msg = f"Metric revision not found: {metric_id}@{version}"
    raise NotFoundError(msg)


def _import_revision(
    definition: MetricDefinition, current: MetricDefinition | None
) -> MetricDefinition:
    expected = current.version if current else 1
    if definition.version != expected:
        msg = f"Metric {definition.id} expected version {definition.version}; current is {expected}"
        raise ConflictError(msg)
    if current and current != definition:
        return definition.model_copy(update={"version": current.version + 1})
    return definition
