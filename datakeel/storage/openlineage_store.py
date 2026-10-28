# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Atomically ingest authenticated OpenLineage observations without another fact store."""

from hashlib import sha256

from datakeel.core.catalog_identity import catalog_id
from datakeel.core.metadata_imports import MetadataImportBatch
from datakeel.core.models import LineageEvent
from datakeel.core.orchestration import (
    OpenLineageNamespace,
    OpenLineageReceipt,
    OpenLineageRunEvent,
    openlineage_job_id,
)
from datakeel.core.orchestration_catalog import dataset_object, resolve_dataset
from datakeel.storage.catalog_locks import lock_catalog
from datakeel.storage.database import Database
from datakeel.storage.events import all_events, append_event
from datakeel.storage.metadata_store import publish_metadata_in_session
from datakeel.storage.openlineage_projection import (
    dataset_snapshot,
    effective_runs,
    job_history,
    job_snapshot,
)

_RUN_STATES = {
    "START": "RUNNING",
    "RUNNING": "RUNNING",
    "COMPLETE": "COMPLETED",
    "ABORT": "ABORT",
    "FAIL": "FAILED",
    "OTHER": "OTHER",
}


def _key(event: OpenLineageRunEvent) -> str:
    identity = catalog_id(event.job.namespace, event.job.name, event.run.runId, event.eventType)
    return f"openlineage:{sha256(identity.encode()).hexdigest()}"


def _observation(
    event: OpenLineageRunEvent, mappings: dict[str, OpenLineageNamespace]
) -> LineageEvent:
    tables = {
        (dataset.namespace, dataset.name): dataset_object(
            dataset, resolve_dataset(dataset, mappings), "openlineage"
        )
        for dataset in (*event.inputs, *event.outputs)
    }
    return LineageEvent(
        idempotency_key=_key(event),
        event_type=event.eventType,
        operator="OPENLINEAGE_RUN",
        source_module="openlineage",
        source_ref=openlineage_job_id(event.job),
        inputs=[tables[(dataset.namespace, dataset.name)].asset_ref for dataset in event.inputs],
        outputs=[tables[(dataset.namespace, dataset.name)].asset_ref for dataset in event.outputs],
        params={"openlineage": event.model_dump(mode="json")},
        run_state=_RUN_STATES[event.eventType],
        occurred_at=event.eventTime,
    )


def ingest_openlineage(
    db: Database,
    event: OpenLineageRunEvent,
    mappings: dict[str, OpenLineageNamespace] | None = None,
) -> OpenLineageReceipt:
    """Fence duplicate checks, run append and all catalog projections in one transaction."""
    mappings = mappings or {}
    observation = _observation(event, mappings)
    job_id = openlineage_job_id(event.job)
    with db.session() as session:
        db.lock_writes(session)
        lock_catalog(session)
        events = all_events(session)
        previous = next((value for value in events if value.idempotency_key == _key(event)), None)
        inserted = previous is None
        if inserted:
            append_event(session, observation)
            events.append(observation)
            for dataset in (*event.inputs, *event.outputs):
                snapshot = dataset_snapshot(dataset, event, all_events(session), mappings)
                publish_metadata_in_session(session, MetadataImportBatch(snapshot=snapshot))
            snapshot = job_snapshot(job_history(events, job_id), mappings)
            publish_metadata_in_session(session, MetadataImportBatch(snapshot=snapshot))
        history = job_history(events, job_id)
        state = next(
            value for value in effective_runs(history) if value.run.runId == event.run.runId
        )
        session.commit()
    return OpenLineageReceipt(
        inserted=inserted,
        event_id=previous.event_id if previous else observation.event_id,
        job_id=job_id,
        run_id=event.run.runId,
        state=state.eventType,
        occurred_at=state.eventTime,
    )
