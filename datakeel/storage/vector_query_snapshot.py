# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Read vector provenance, frozen authorization closure and reports in one transaction."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from datakeel.core.errors import NotFoundError
from datakeel.core.models import AssetRef, LineageEvent
from datakeel.core.vector_models import (
    VECTOR_OPERATORS,
    VectorAttempt,
    VectorCounts,
    VectorError,
    VectorPrepared,
    vector_hash,
)
from datakeel.core.vector_results import VectorNodeReport, VectorTaskReport
from datakeel.dataset_store.rows import EventRow, VersionRow
from datakeel.pipeline.models import Node, Pipeline
from datakeel.storage.action_rows import ActionPlanRow, ActionRunRow
from datakeel.storage.evidence_artifacts import load_bundle
from datakeel.storage.vector_references import resolve_references
from datakeel.storage.vector_rows import VectorAttemptRow, VectorCacheRow
from datakeel.worker_store.rows import TaskRow


def query_task(session: Session, run_id: str, dataset_id: str | None) -> TaskRow:
    """Keep task identity private until its complete frozen sources are authorized."""
    task = session.get(TaskRow, run_id)
    if (
        task is None
        or (dataset_id is not None and dataset_id != task.dataset_id)
        or task.pipeline is None
        or not any(n.get("operator") in VECTOR_OPERATORS for n in task.pipeline.get("nodes", []))
    ):
        msg = "Vector run not found"
        raise NotFoundError(msg)
    return task


def query_events(session: Session, run_id: str) -> tuple[LineageEvent, ...]:
    """Return only vector provenance, with deterministic event ordering."""
    return tuple(
        LineageEvent.model_validate(row.payload)
        for row in session.scalars(
            select(EventRow)
            .where(EventRow.payload["source_ref"].as_string() == run_id)
            .order_by(EventRow.event_id)
        )
        if row.payload.get("operator") in VECTOR_OPERATORS
    )


def query_sources(session: Session, task: TaskRow) -> tuple[AssetRef, ...]:
    """Include failed inputs and all frozen T/R even when no facts were published."""
    refs = [AssetRef(asset_id=task.dataset_id)]
    version = session.get(VersionRow, task.input_version_id) if task.input_version_id else None
    if version:
        refs.extend(
            AssetRef(asset_type="file", asset_id=raw["id"], version=version.id)
            for raw in version.manifest
        )
    run = session.scalar(select(ActionRunRow).where(ActionRunRow.task_id == task.id))
    plan = session.get(ActionPlanRow, run.plan_id) if run else None
    prepared = plan.payload.get("canonical_params", {}).get("vector_prepared") if plan else None
    if prepared:
        frozen = VectorPrepared.model_validate(prepared)
        refs.extend(
            m.subject
            for selection in frozen.selections
            if selection.scope
            for m in (*selection.scope.targets, *selection.scope.references)
        )
    return tuple(dict.fromkeys(refs))


def query_report(
    session: Session, task: TaskRow, events: tuple[LineageEvent, ...]
) -> VectorTaskReport:
    """Preserve failure counts, pending state and durable fake attempt accounting."""
    nodes = tuple(
        VectorNodeReport.model_validate(event.quality["vector"])
        for event in events
        if "vector" in event.quality
    ) + tuple(
        VectorNodeReport(
            status="failed",
            reason=str(event.quality.get("vector_failure_reason")),
            counts=VectorCounts.model_validate(event.quality["vector_failure_counts"]),
        )
        for event in events
        if "vector_failure_counts" in event.quality
    )
    status = (
        "failed"
        if task.state == "FAILED"
        else "cancelled"
        if task.state == "CANCELLED"
        else "pending"
        if task.state != "COMPLETED"
        else "partial_success"
        if any(n.status == "partial_success" for n in nodes)
        else "insufficient"
        if any(n.status == "insufficient" for n in nodes)
        else "success"
    )
    attempts = tuple(
        VectorAttempt.model_validate(
            {
                "id": row.id,
                "state": row.state,
                "token_bound": row.token_bound,
                "reserved_nanos": row.reserved_nanos,
                "usage": row.payload.get("usage"),
                "response_id": row.payload.get("response_id"),
                "reason": row.payload.get("reason"),
            }
        )
        for row in session.scalars(
            select(VectorAttemptRow)
            .where(VectorAttemptRow.task_id == task.id)
            .order_by(VectorAttemptRow.id)
        )
    )
    return VectorTaskReport(
        status=status,
        reason=task.error.removeprefix("VectorError: ")
        if task.error
        else "vector_insufficient_samples"
        if status == "insufficient"
        else None,
        nodes=nodes,
        attempts=attempts,
    )


def reference_states(session: Session, events: tuple[LineageEvent, ...]) -> tuple[bool, ...]:
    """Validate frozen R even for a successful gap run that produced no candidates."""
    states: list[bool] = []
    for event in events:
        if event.operator != "evidence.coverage_gap" or "knowledge_bundle" not in event.params:
            continue
        scope = load_bundle(event).vector_scope
        node = Node(
            id="reference",
            operator="evidence.coverage_gap",
            inputs={"files": "$input.files"},
            params=event.params["parameters"],
        )
        try:
            current = resolve_references(
                session, Pipeline(nodes=[node], outputs=["reference.files"])
            )
            states.append(scope is not None and current[0].members == scope.references)
        except (VectorError, NotFoundError):
            states.append(False)
    return tuple(states)


def reference_digest(events: tuple[LineageEvent, ...]) -> str:
    """Hash complete frozen R, including runs with zero coverage findings."""
    return vector_hash(
        [
            [m.model_dump(mode="json") for m in scope.references]
            for event in events
            if event.operator == "evidence.coverage_gap" and "knowledge_bundle" in event.params
            if (scope := load_bundle(event).vector_scope) is not None
        ]
    )


def publication_current(session: Session, events: tuple[LineageEvent, ...]) -> tuple[bool, ...]:
    """Recognize superseding global publications even when the old result had no facts."""
    return tuple(
        producer == event.event_id
        for event in events
        if "knowledge_bundle" in event.params
        for product in load_bundle(event).vector_products
        if product.kind == "global"
        if (
            producer := session.scalar(
                select(VectorCacheRow.producer_event_id).where(
                    VectorCacheRow.namespace_key
                    == f"{product.mode}:{product.implementation}:{product.kind}:{product.key}"
                )
            )
        )
        is not None
    )
