# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Derive OpenLineage job and dataset metadata from authoritative run events."""

from collections import defaultdict
from datetime import datetime

from datakeel.core.catalog_models import CatalogLink, CatalogObject, CatalogSnapshot
from datakeel.core.catalog_projection import snapshot_events
from datakeel.core.metadata_imports import ExternalMetadata
from datakeel.core.models import AssetRef, JsonDocument, LineageEvent
from datakeel.core.orchestration import (
    TERMINAL_EVENTS,
    OpenLineageDataset,
    OpenLineageNamespace,
    OpenLineageRunEvent,
    openlineage_job_id,
)
from datakeel.core.orchestration_catalog import dataset_columns, dataset_object, resolve_dataset


def job_history(events: list[LineageEvent], job_id: str) -> tuple[OpenLineageRunEvent, ...]:
    """Decode only this job's immutable standard-event payloads."""
    return tuple(
        OpenLineageRunEvent.model_validate(event.params["openlineage"])
        for event in events
        if event.operator == "OPENLINEAGE_RUN"
        and event.source_ref == job_id
        and "openlineage" in event.params
    )


def effective_runs(history: tuple[OpenLineageRunEvent, ...]) -> tuple[OpenLineageRunEvent, ...]:
    """Rank terminal over in-progress over OTHER, using event time within one rank."""
    runs: dict[str, list[OpenLineageRunEvent]] = defaultdict(list)
    for event in history:
        runs[event.run.runId].append(event)
    states: list[OpenLineageRunEvent] = []
    for values in runs.values():
        terminal = [event for event in values if event.eventType in TERMINAL_EVENTS]
        progress = [event for event in values if event.eventType in {"START", "RUNNING"}]
        states.append(
            max(
                terminal or progress or values,
                key=lambda event: (event.eventTime, event.eventType == "FAIL"),
            )
        )
    return tuple(sorted(states, key=lambda event: (event.eventTime, event.run.runId), reverse=True))


def job_snapshot(
    history: tuple[OpenLineageRunEvent, ...],
    mappings: dict[str, OpenLineageNamespace],
) -> CatalogSnapshot:
    """Project latest job status, bounded run records and declared dataset dependencies."""
    runs = effective_runs(history)
    latest = runs[0]
    job_id = openlineage_job_id(latest.job)
    successes = [event for event in runs if event.eventType == "COMPLETE"]
    metadata = ExternalMetadata(
        system="openlineage",
        unique_id=job_id,
        details=JsonDocument(
            {
                "namespace": latest.job.namespace,
                "state": latest.eventType,
                "run_id": latest.run.runId,
                "last_run_time": latest.eventTime.isoformat(),
                "last_success": successes[0].eventTime.isoformat() if successes else None,
                "facets": latest.job.facets.root,
                "runs": [
                    {
                        "run_id": event.run.runId,
                        "state": event.eventType,
                        "event_time": event.eventTime.isoformat(),
                    }
                    for event in runs[:100]
                ],
            }
        ),
    )
    job = CatalogObject(
        asset_ref=AssetRef(asset_type="job", asset_id=job_id, display_name=latest.job.name),
        name=latest.job.name,
        source_id=f"openlineage:{latest.job.namespace}",
        properties=JsonDocument({"integration": metadata.model_dump(mode="json")}),
    )
    links: dict[tuple[str, str], CatalogLink] = {}
    for event in history:
        for datasets, output in ((event.inputs, False), (event.outputs, True)):
            for dataset in datasets:
                table = dataset_object(dataset, resolve_dataset(dataset, mappings), "openlineage")
                source, target = (job, table) if output else (table, job)
                link = CatalogLink(source=source.asset_ref, target=target.asset_ref, kind="derived")
                links[(source.asset_ref.asset_id, target.asset_ref.asset_id)] = link
    return CatalogSnapshot(
        scope=f"metadata:openlineage:job:{job_id}", objects=(job,), links=tuple(links.values())
    )


def _merge_facets(
    old: JsonDocument, dataset: OpenLineageDataset, event: OpenLineageRunEvent
) -> JsonDocument:
    facets = old.root.get("facets", {})
    times = old.root.get("facet_times", {})
    merged = dict(facets) if isinstance(facets, dict) else {}
    clocks = dict(times) if isinstance(times, dict) else {}
    for key, value in dataset.facets.root.items():
        timestamp = clocks.get(key)
        previous_time = datetime.fromisoformat(timestamp) if isinstance(timestamp, str) else None
        if previous_time is None or event.eventTime >= previous_time:
            merged[key] = value
            clocks[key] = event.eventTime.isoformat()
    return JsonDocument({"facets": merged, "facet_times": clocks})


def dataset_snapshot(
    dataset: OpenLineageDataset,
    event: OpenLineageRunEvent,
    events: list[LineageEvent],
    mappings: dict[str, OpenLineageNamespace],
) -> CatalogSnapshot:
    """Merge sparse facets and monotonically retain the last successful output time."""
    resolved = resolve_dataset(dataset, mappings)
    table = dataset_object(dataset, resolved, "openlineage")
    scope = f"metadata:openlineage:dataset:{table.asset_ref.asset_id}"
    prior = next(
        (snapshot for _, snapshot in reversed(snapshot_events(events)) if snapshot.scope == scope),
        CatalogSnapshot(scope=scope),
    )
    previous = next((obj for obj in prior.objects if obj.asset_ref.asset_type == "table"), None)
    old = (
        ExternalMetadata.model_validate(previous.properties.root["integration"]).details.root
        if previous
        else {}
    )
    merged = _merge_facets(JsonDocument(old), dataset, event)
    facets = merged.root["facets"]
    is_output = dataset in event.outputs
    dataset = dataset.model_copy(update={"facets": JsonDocument.model_validate(facets)})
    freshness = old.get("last_success")
    if event.eventType == "COMPLETE" and is_output:
        previous_time = datetime.fromisoformat(freshness) if isinstance(freshness, str) else None
        freshness = (
            max(previous_time, event.eventTime).isoformat()
            if previous_time
            else (event.eventTime.isoformat())
        )
    details = JsonDocument(
        {
            **merged.root,
            "placeholder": "schema" not in dataset.facets.root,
            "last_success": freshness,
        }
    )
    table = dataset_object(dataset, resolved, "openlineage", details)
    columns = dataset_columns(dataset, table)
    links = tuple(
        CatalogLink(source=table.asset_ref, target=c.asset_ref, kind="contains") for c in columns
    )
    return CatalogSnapshot(scope=scope, objects=(table, *columns), links=links)
