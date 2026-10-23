# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Evaluate bounded object-set predicates against current authoritative facts."""

from pydantic import JsonValue
from sqlalchemy import select
from sqlalchemy.orm import Session

from datakeel.core.errors import NotFoundError
from datakeel.ontology.models import FrozenManifest, FrozenObject, ObjectSet, PropertyFilter
from datakeel.storage.database import Database, DatasetRow
from datakeel.storage.evidence_filters import select_evidence
from datakeel.storage.evidence_snapshot import EvidenceSnapshot, read_snapshot
from datakeel.storage.object_projection import content_digest, has_evidence_sources, project_objects


def _lookup(properties: dict[str, JsonValue], field: str) -> tuple[bool, JsonValue]:
    current: JsonValue = properties
    for name in field.split("."):
        if not isinstance(current, dict) or name not in current:
            return False, None
        current = current[name]
    return True, current


def _equal(left: JsonValue, right: JsonValue) -> bool:
    if (
        isinstance(left, int | float)
        and not isinstance(left, bool)
        and isinstance(right, int | float)
        and not isinstance(right, bool)
    ):
        return left == right
    return content_digest(left) == content_digest(right)


def _ordered(actual: JsonValue, expected: JsonValue, operator: str) -> bool:
    if isinstance(actual, bool) or not isinstance(actual, int | float):
        return False
    if isinstance(expected, bool) or not isinstance(expected, int | float):
        return False
    if operator == "lt":
        return actual < expected
    if operator == "lte":
        return actual <= expected
    if operator == "gt":
        return actual > expected
    return actual >= expected


def _matches(properties: dict[str, JsonValue], rule: PropertyFilter) -> bool:
    found, actual = _lookup(properties, rule.field)
    if not found:
        return False
    if rule.operator == "eq":
        return _equal(actual, rule.value)
    if rule.operator == "ne":
        return not _equal(actual, rule.value)
    if rule.operator == "in":
        return isinstance(rule.value, list) and any(_equal(actual, item) for item in rule.value)
    if rule.operator == "contains":
        return (
            rule.value in actual
            if isinstance(actual, str) and isinstance(rule.value, str)
            else isinstance(actual, list) and any(_equal(item, rule.value) for item in actual)
        )
    return _ordered(actual, rule.value, rule.operator)


def _selected(value: FrozenObject, query: ObjectSet) -> bool:
    if not all(_matches(value.properties, rule) for rule in query.filters):
        return False
    quality = value.properties.get("quality")
    if query.quality_min is not None and (
        not isinstance(quality, int | float) or quality < query.quality_min
    ):
        return False
    return not (
        query.quality_max is not None
        and (not isinstance(quality, int | float) or quality > query.quality_max)
    )


def matching_objects_in_session(
    session: Session, query: ObjectSet, snapshot: EvidenceSnapshot | None = None
) -> list[FrozenObject]:
    """Resolve all matching versions before a caller applies its selection or view limit."""
    statement = select(DatasetRow).order_by(DatasetRow.id)
    if query.dataset_id:
        statement = statement.where(DatasetRow.id == query.dataset_id)
    datasets = list(session.scalars(statement))
    if query.dataset_id and not datasets:
        msg = "Dataset not found"
        raise NotFoundError(msg)
    if snapshot is None:
        has_evidence = query.object_type in {"file", "artifact"} and (
            bool(query.assertion_filters)
            or query.has_near_duplicate_in is not None
            or has_evidence_sources(session, datasets, query)
        )
        snapshot = (
            read_snapshot(session, include_peer_splits=query.has_near_duplicate_in is not None)
            if has_evidence
            else EvidenceSnapshot(subjects={})
        )
    projected = project_objects(session, datasets, query, snapshot)
    objects = [
        value for value in select_evidence(projected, query, snapshot) if _selected(value, query)
    ]
    objects.sort(key=lambda value: (value.asset_ref.asset_id, value.asset_ref.version or ""))
    return objects


def evaluate_in_session(
    session: Session, query: ObjectSet, snapshot: EvidenceSnapshot | None = None
) -> FrozenManifest:
    """Freeze exact matching revisions inside the caller's existing transaction."""
    objects = matching_objects_in_session(session, query, snapshot)
    selected = objects[: query.limit]
    return FrozenManifest(
        query=query,
        objects=selected,
        state_digest=content_digest(
            {
                "query": query.model_dump(mode="json"),
                "objects": [value.model_dump(mode="json") for value in objects],
            }
        ),
        total_bytes=sum(value.size for value in selected),
        truncated=len(objects) > query.limit,
    )


def evaluate(db: Database, query: ObjectSet) -> FrozenManifest:
    """Resolve a read-only object query using a short-lived database session."""
    with db.session() as session:
        return evaluate_in_session(session, query)
