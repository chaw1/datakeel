# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Prepare offline Airflow REST v1 inventory without importing or executing Airflow."""

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from datakeel.catalog.importers.helpers import contains, metadata_object
from datakeel.core.catalog_identity import catalog_id
from datakeel.core.catalog_models import (
    CatalogLink,
    CatalogObject,
    CatalogSnapshot,
    SourceProperties,
)
from datakeel.core.errors import ValidationError
from datakeel.core.metadata_imports import (
    AirflowImportRequest,
    ExternalMetadata,
    MetadataImportBatch,
)
from datakeel.core.models import AssetRef, JsonDocument
from datakeel.core.orchestration_airflow import (
    AirflowDag,
    AirflowDataset,
    AirflowExport,
    AirflowRun,
    AirflowTask,
)
from datakeel.core.orchestration_catalog import dataset_from_uri, dataset_object
from datakeel.core.orchestration_sources import (
    UNMATCHED_SOURCE_ID,
    SourceNamespace,
    attribute_dataset,
)

if TYPE_CHECKING:
    from pydantic import JsonValue

Sources = Sequence[SourceNamespace]


def _run_time(run: AirflowRun) -> datetime:
    return (
        run.end_date
        or run.start_date
        or run.logical_date
        or run.execution_date
        or datetime.min.replace(tzinfo=UTC)
    )


def _run_order(run: AirflowRun) -> tuple[datetime, datetime]:
    """Order runs by their logical date, as Airflow and the v1 order_by do.

    Never-started runs or instances (queued, upstream_failed) only carry the logical
    date; comparing it with another run's end time would hide the newest state.
    """
    return (run.logical_date or run.execution_date or _run_time(run), _run_time(run))


def _run_details(runs: tuple[AirflowRun, ...]) -> JsonDocument:
    latest = max(runs, key=_run_order) if runs else None
    successes = [run for run in runs if run.state == "success"]
    last_success = max(successes, key=_run_time) if successes else None
    return JsonDocument(
        {
            "state": latest.state if latest else None,
            "latest_run": latest.model_dump(mode="json") if latest else None,
            "last_success": _run_time(last_success).isoformat() if last_success else None,
        }
    )


def _dag_object(request: AirflowImportRequest, dag: AirflowDag) -> CatalogObject:
    runs = _run_details(dag.dag_runs).root
    metadata = ExternalMetadata(
        system="airflow",
        unique_id=dag.dag_id,
        description=dag.description,
        owner=", ".join(dag.owners) or None,
        tags=tuple(tag if isinstance(tag, str) else tag.name for tag in dag.tags or ()),
        details=JsonDocument(
            {
                **runs,
                "schedule": dag.schedule_interval,
                "timetable_description": dag.timetable_description,
                "is_paused": dag.is_paused,
                "is_active": dag.is_active,
            }
        ),
    )
    name = dag.dag_display_name or dag.dag_id
    return CatalogObject(
        asset_ref=AssetRef(
            asset_type="dag",
            asset_id=catalog_id(request.source_id, "dag", dag.dag_id),
            display_name=name,
        ),
        name=name,
        source_id=request.source_id,
        properties=JsonDocument({"integration": metadata.model_dump(mode="json")}),
    )


def _task_object(
    request: AirflowImportRequest, dag: AirflowDag, task: AirflowTask
) -> CatalogObject:
    runs = tuple(run for run in dag.task_instances if run.task_id == task.task_id)
    metadata = ExternalMetadata(
        system="airflow",
        unique_id=f"{dag.dag_id}.{task.task_id}",
        description=task.doc_md,
        owner=task.owner or ", ".join(dag.owners) or None,
        details=JsonDocument(
            {**_run_details(runs).root, "dag_id": dag.dag_id, "task_id": task.task_id}
        ),
    )
    name = task.task_display_name or task.task_id
    return CatalogObject(
        asset_ref=AssetRef(
            asset_type="airflow_task",
            asset_id=catalog_id(request.source_id, "dag", dag.dag_id, task.task_id),
            display_name=name,
        ),
        name=name,
        source_id=request.source_id,
        properties=JsonDocument({"integration": metadata.model_dump(mode="json")}),
    )


def _dag_entries(export: AirflowExport) -> tuple[AirflowDag, ...]:
    result: list[AirflowDag] = []
    for dag in export.dags:
        tasks = export.tasks.get(dag.dag_id)
        runs = export.dag_runs.get(dag.dag_id)
        instances = export.task_instances.get(dag.dag_id)
        result.append(
            dag.model_copy(
                update={
                    "tasks": tasks.tasks if tasks else dag.tasks,
                    "dag_runs": runs.dag_runs if runs else dag.dag_runs,
                    "task_instances": instances.task_instances if instances else dag.task_instances,
                }
            )
        )
    return tuple(result)


def _dataset(sources: Sources, uri: str, last_success: str | None) -> CatalogObject:
    dataset = dataset_from_uri(uri)
    resolved = attribute_dataset(dataset, sources)
    details: dict[str, JsonValue] = {"uri": uri, "last_success": last_success}
    if resolved.location is not None:
        details["unmatched_source"] = True
    return dataset_object(dataset, resolved, "airflow", JsonDocument(details))


def _link(source: CatalogObject, target: CatalogObject, kind: str = "derived") -> CatalogLink:
    return CatalogLink.model_validate(
        {"source": source.asset_ref, "target": target.asset_ref, "kind": kind}
    )


def _task_datasets(
    sources: Sources, task: AirflowTask, node: CatalogObject
) -> tuple[tuple[CatalogObject, ...], tuple[CatalogLink, ...]]:
    metadata = ExternalMetadata.model_validate(node.properties.root["integration"])
    last_success = metadata.details.root.get("last_success")
    freshness = last_success if isinstance(last_success, str) else None
    objects: list[CatalogObject] = []
    links: list[CatalogLink] = []
    for values, output in ((task.inlets, False), (task.outlets, True)):
        for value in values:
            uri = value if isinstance(value, str) else value.uri
            table = _dataset(sources, uri, freshness if output else None)
            objects.append(table)
            links.append(_link(node, table) if output else _link(table, node))
    return tuple(objects), tuple(links)


def _dag_inventory(
    request: AirflowImportRequest, dag: AirflowDag, sources: Sources
) -> tuple[tuple[CatalogObject, ...], tuple[CatalogLink, ...]]:
    parent = _dag_object(request, dag)
    tasks = {task.task_id: _task_object(request, dag, task) for task in dag.tasks}
    if len(tasks) != len(dag.tasks):
        msg = f"Airflow DAG {dag.dag_id} contains duplicate task IDs"
        raise ValidationError(msg)
    objects = [parent, *tasks.values()]
    links = [_link(parent, task, "contains") for task in tasks.values()]
    for task in dag.tasks:
        extra, edges = _task_datasets(sources, task, tasks[task.task_id])
        objects.extend(extra)
        links.extend(edges)
        for target in task.downstream_task_ids:
            if target not in tasks:
                msg = f"Airflow task {task.task_id} references unknown downstream task {target}"
                raise ValidationError(msg)
            links.append(_link(tasks[task.task_id], tasks[target]))
    return tuple(objects), tuple(links)


def _retain_freshness(old: CatalogObject | None, current: CatalogObject) -> CatalogObject:
    if old is None or current.asset_ref.asset_type != "table":
        return current
    previous = ExternalMetadata.model_validate(old.properties.root["integration"])
    metadata = ExternalMetadata.model_validate(current.properties.root["integration"])
    times = [previous.details.root.get("last_success"), metadata.details.root.get("last_success")]
    known = [datetime.fromisoformat(value) for value in times if isinstance(value, str)]
    if not known:
        return current
    metadata = metadata.model_copy(
        update={
            "details": JsonDocument(
                {**metadata.details.root, "last_success": max(known).isoformat()}
            )
        }
    )
    return current.model_copy(
        update={
            "properties": JsonDocument(
                {**current.properties.root, "integration": metadata.model_dump(mode="json")}
            )
        }
    )


def _dataset_inventory(
    request: AirflowImportRequest,
    dataset: AirflowDataset,
    objects: dict[str, CatalogObject],
    sources: Sources,
) -> tuple[CatalogObject, tuple[CatalogLink, ...]]:
    table = _dataset(sources, dataset.uri, None)
    links: list[CatalogLink] = []
    for reference in dataset.producing_tasks:
        identity = catalog_id(request.source_id, "dag", reference.dag_id, reference.task_id or "")
        if identity in objects:
            producer = objects[identity]
            metadata = ExternalMetadata.model_validate(producer.properties.root["integration"])
            freshness = metadata.details.root.get("last_success")
            if isinstance(freshness, str):
                table = _retain_freshness(table, _dataset(sources, dataset.uri, freshness))
            links.append(_link(producer, table))
    for reference in dataset.consuming_dags:
        identity = catalog_id(request.source_id, "dag", reference.dag_id)
        if identity in objects:
            links.append(_link(table, objects[identity]))
    return table, tuple(links)


def _unmatched_source(objects: dict[str, CatalogObject]) -> tuple[CatalogLink, ...]:
    """File datasets no known source claims under one explicit placeholder source."""
    unmatched = [
        item
        for item in objects.values()
        if item.source_id == UNMATCHED_SOURCE_ID
        and ExternalMetadata.model_validate(item.properties.root["integration"]).details.root.get(
            "unmatched_source"
        )
        is True
    ]
    if not unmatched:
        return ()
    source = metadata_object(
        "source", catalog_id(UNMATCHED_SOURCE_ID), "airflow", SourceProperties(dialect="unknown")
    )
    objects[source.asset_ref.asset_id] = source
    return tuple(contains(source, item) for item in unmatched)


def prepare_airflow(request: AirflowImportRequest, sources: Sources = ()) -> MetadataImportBatch:
    """Parse documented offline v1 endpoint exports into one incrementally owned scope.

    Dataset URIs are attributed to ``sources`` by normalized namespace and database;
    the rest are filed under the ``airflow`` placeholder source as unmatched.
    """
    export = AirflowExport.model_validate(request.document.root)
    if len({dag.dag_id for dag in export.dags}) != len(export.dags):
        msg = "Airflow exports require unique DAG IDs"
        raise ValidationError(msg)
    objects: dict[str, CatalogObject] = {}
    links: list[CatalogLink] = []
    for dag in _dag_entries(export):
        entries, edges = _dag_inventory(request, dag, sources)
        for item in entries:
            identity = item.asset_ref.asset_id
            objects[identity] = _retain_freshness(objects.get(identity), item)
        links.extend(edges)
    for dataset in export.datasets:
        table, edges = _dataset_inventory(request, dataset, objects, sources)
        identity = table.asset_ref.asset_id
        objects[identity] = _retain_freshness(objects.get(identity), table)
        links.extend(edges)
    links.extend(_unmatched_source(objects))
    unique_links = {(link.kind, link.source.asset_id, link.target.asset_id): link for link in links}
    return MetadataImportBatch(
        snapshot=CatalogSnapshot(
            scope=f"metadata:airflow:{request.source_id}",
            objects=tuple(objects.values()),
            links=tuple(unique_links.values()),
        )
    )
