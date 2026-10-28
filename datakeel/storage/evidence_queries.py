# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Read-only evidence selection, deterministic pagination, detail, and explanations."""

from datakeel.core.data_asset_models import AccessContext
from datakeel.core.errors import NotFoundError, ValidationError
from datakeel.core.evidence_models import AssertionStatus, EvidenceValue
from datakeel.core.models import AssetRef
from datakeel.evidence.presentation import explain, present_sample
from datakeel.evidence.query_models import (
    EvidenceExplanation,
    EvidenceQuery,
    EvidenceQueryResult,
    EvidenceSample,
)
from datakeel.ontology.models import FrozenObject, ObjectSet, PropertyFilter
from datakeel.storage.data_asset_reads import authorize_query
from datakeel.storage.database import Database
from datakeel.storage.evidence_snapshot import EvidenceSnapshot, read_snapshot
from datakeel.storage.object_queries import evaluate_in_session, matching_objects_in_session


def _version_order(value: FrozenObject) -> tuple[float, str]:
    created = value.properties.get("created_at")
    return float(created) if isinstance(created, int | float) else 0, value.asset_ref.version or ""


def _review_order(
    value: FrozenObject, snapshot: EvidenceSnapshot, statuses: set[AssertionStatus]
) -> tuple[int, int, str]:
    assertions = [
        item
        for item in snapshot.observations(value.asset_ref).assertions
        if item.status in statuses
    ]
    return (
        -sum(
            isinstance(item.object, EvidenceValue) and item.object.value == "unknown"
            for item in assertions
        ),
        -sum(item.status == "candidate" for item in assertions),
        value.asset_ref.asset_id,
    )


def _sorted_objects(
    values: list[FrozenObject],
    query: EvidenceQuery,
    snapshot: EvidenceSnapshot,
    statuses: set[AssertionStatus],
) -> list[FrozenObject]:
    if query.sort == "review":
        return sorted(values, key=lambda value: _review_order(value, snapshot, statuses))
    if query.sort == "filename":
        return sorted(
            values,
            key=lambda value: (
                str(value.properties.get("filename", "")).casefold(),
                value.asset_ref.asset_id,
            ),
        )
    if query.sort == "quality":
        return sorted(values, key=lambda value: (_quality(value), value.asset_ref.asset_id))
    return sorted(values, key=lambda value: value.asset_ref.asset_id)


def _quality(value: FrozenObject) -> float:
    quality = value.properties.get("quality")
    return float(quality) if isinstance(quality, int | float) else 0


def _after_cursor(objects: list[FrozenObject], query: EvidenceQuery) -> list[FrozenObject]:
    if query.cursor is None:
        return objects
    if query.sort == "asset":
        return [value for value in objects if value.asset_ref.asset_id > query.cursor]
    for index, value in enumerate(objects):
        if value.asset_ref.asset_id == query.cursor:
            return objects[index + 1 :]
    msg = "Evidence cursor no longer belongs to the selected results; restart pagination"
    raise ValidationError(msg)


def query_evidence(
    db: Database, query: EvidenceQuery, *, access: AccessContext | None = None
) -> EvidenceQueryResult:
    """Sort the complete selected set before pagination, retaining asset order by default."""
    statuses: set[AssertionStatus] = {"candidate", "accepted"}
    if query.assertion_filters:
        statuses = {status for rule in query.assertion_filters for status in rule.status}
    with db.session() as session:
        snapshot = read_snapshot(
            session, include_peer_splits=query.has_near_duplicate_in is not None
        )
        selected = matching_objects_in_session(session, query.selection(), snapshot)
        # A cursor identifies an asset, so each asset uses its latest matching source version.
        unique = {value.asset_ref.asset_id: value for value in sorted(selected, key=_version_order)}
        objects = _sorted_objects(list(unique.values()), query, snapshot, statuses)[: query.limit]
        remaining = _after_cursor(objects, query)
        page = remaining[: query.page_size]
        items = [
            present_sample(
                value,
                [
                    assertion
                    for assertion in snapshot.observations(value.asset_ref).assertions
                    if assertion.status in statuses
                ],
            )
            for value in page
        ]
    refs = [ref for item in items for ref in sample_refs(item)]
    if query.dataset_id:
        refs.append(AssetRef(asset_id=query.dataset_id))
    refs.extend(AssetRef(asset_type="version", asset_id=value) for value in query.version_ids)
    authorize_query(db, tuple(refs), access)
    return EvidenceQueryResult(
        items=items,
        total=len(objects),
        truncated=len(unique) > query.limit,
        next_cursor=page[-1].asset_ref.asset_id if len(remaining) > len(page) else None,
    )


def get_evidence(
    db: Database,
    asset_id: str,
    version_id: str | None = None,
    *,
    access: AccessContext | None = None,
) -> EvidenceSample:
    """Return all active statuses for one original sample, including explicit rejections."""
    with db.session() as session:
        snapshot = read_snapshot(session)
        selected = evaluate_in_session(
            session,
            ObjectSet(
                filters=[PropertyFilter(field="id", value=asset_id)],
                version_ids=[version_id] if version_id else [],
                limit=1,
            ),
            snapshot,
        )
        if not selected.objects:
            msg = "Evidence sample not found"
            raise NotFoundError(msg)
        value = selected.objects[0]
        sample = present_sample(value, list(snapshot.observations(value.asset_ref).assertions))
    authorize_query(db, sample_refs(sample), access)
    return sample


def explain_sample(
    db: Database,
    asset_id: str,
    version_id: str | None = None,
    *,
    access: AccessContext | None = None,
) -> EvidenceExplanation:
    """Expose the actual assertion states rather than inferring absent or unknown answers."""
    return explain(get_evidence(db, asset_id, version_id, access=access))


def sample_refs(sample: EvidenceSample) -> tuple[AssetRef, ...]:
    """Include original and neighboring sources disclosed by one evidence card."""
    return (
        sample.asset_ref,
        *(neighbor.asset_ref for neighbor in sample.near_duplicates),
        *(anchor.asset_ref for assertion in sample.assertions for anchor in assertion.anchors),
    )
