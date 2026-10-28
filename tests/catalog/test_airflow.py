# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Generated offline Airflow v1 imports preserve runtime and dependency evidence."""

from pathlib import Path

import pytest

from datakeel.catalog.importers.airflow import prepare_airflow
from datakeel.core.errors import ValidationError
from datakeel.core.metadata_imports import AirflowImportRequest, ExternalMetadata
from datakeel.core.models import JsonDocument
from datakeel.core.orchestration import OpenLineageNamespace
from datakeel.storage.catalog_store import read_snapshot
from datakeel.storage.database import Database
from datakeel.storage.metadata_store import publish_metadata

FIXTURE = Path(__file__).parents[1] / "fixtures" / "metadata" / "airflow-v1.json"
# The fixture's analytics database is the catalog source "warehouse".
SOURCES = (
    (
        "postgres://warehouse.example",
        OpenLineageNamespace(source_id="warehouse", database="analytics"),
    ),
)


def request(document: JsonDocument | None = None) -> AirflowImportRequest:
    """Read a synthetic v1 response export."""
    return AirflowImportRequest(
        source_id="warehouse",
        document=document or JsonDocument.model_validate_json(FIXTURE.read_text()),
    )


def test_airflow_import_preserves_schedule_owner_status_and_freshness(db: Database) -> None:
    """DAG/task state and successful output freshness survive transactional readback."""
    batch = prepare_airflow(sources=SOURCES, request=request())
    result = publish_metadata(db, batch)
    with db.session() as session:
        objects = {item.asset_ref.asset_id: item for item in read_snapshot(session).objects}
    dag = ExternalMetadata.model_validate(
        objects["warehouse/dag/daily_orders"].properties["integration"]
    )
    task = ExternalMetadata.model_validate(
        objects["warehouse/dag/daily_orders/build"].properties["integration"]
    )
    table = ExternalMetadata.model_validate(
        objects["warehouse/public/orders"].properties["integration"]
    )
    assert result.new == 6
    assert dag.owner == "analytics"
    assert dag.tags == ("finance",)
    assert dag.details["schedule"] == {"__type": "CronExpression", "value": "0 6 * * *"}
    assert dag.details["state"] == "failed"
    assert dag.details["last_success"] == "2026-10-25T06:10:00+00:00"
    assert task.description == "Build the reporting table"
    assert task.details["state"] == "failed"
    assert table.details["last_success"] == "2026-10-25T06:10:00+00:00"


def test_airflow_import_preserves_explicit_inlets_outlets_and_dependencies() -> None:
    """Task dependencies remain directed alongside explicit dataset flow edges."""
    snapshot = prepare_airflow(sources=SOURCES, request=request()).snapshot
    edges = {(edge.source.asset_id, edge.target.asset_id, edge.kind) for edge in snapshot.links}
    assert ("warehouse/raw/orders", "warehouse/dag/daily_orders/extract", "derived") in edges
    assert ("warehouse/dag/daily_orders/build", "warehouse/public/orders", "derived") in edges
    assert (
        "warehouse/dag/daily_orders/extract",
        "warehouse/dag/daily_orders/build",
        "derived",
    ) in edges
    assert ("warehouse/public/orders", "warehouse/dag/daily_orders", "derived") in edges
    assert ("warehouse/dag/daily_orders", "warehouse/dag/daily_orders/build", "contains") in edges


def test_airflow_incremental_replay_and_soft_deleted_tasks(db: Database) -> None:
    """An identical replay is event-free and a removed inventory remains as tombstones."""
    batch = prepare_airflow(sources=SOURCES, request=request())
    publish_metadata(db, batch)
    replay = publish_metadata(db, batch)
    removed = publish_metadata(
        db, prepare_airflow(sources=SOURCES, request=request(JsonDocument({"dags": []})))
    )
    assert replay.new == replay.changed == replay.deleted == 0
    assert replay.event_id is None
    assert removed.deleted == 6
    with db.session() as session:
        assert all(item.properties["source_deleted"] for item in read_snapshot(session).objects)


def test_airflow_nested_export_and_absent_run_details() -> None:
    """A minimal nested offline export does not fabricate runtime observations."""
    document = JsonDocument(
        {"dags": [{"dag_id": "sample", "tags": ["demo"], "tasks": [{"task_id": "one"}]}]}
    )
    snapshot = prepare_airflow(sources=SOURCES, request=request(document)).snapshot
    dag = ExternalMetadata.model_validate(snapshot.objects[0].properties["integration"])
    assert dag.details["last_success"] is None
    assert dag.details["state"] is None
    assert dag.tags == ("demo",)
    assert snapshot.objects[1].asset_ref.asset_type == "airflow_task"


@pytest.mark.parametrize(
    ("document", "message"),
    [
        ({"dags": [{"dag_id": "one"}, {"dag_id": "one"}]}, "unique DAG"),
        (
            {"dags": [{"dag_id": "one", "tasks": [{"task_id": "x"}, {"task_id": "x"}]}]},
            "duplicate task",
        ),
        (
            {
                "dags": [
                    {
                        "dag_id": "one",
                        "tasks": [{"task_id": "x", "downstream_task_ids": ["missing"]}],
                    }
                ]
            },
            "unknown downstream",
        ),
    ],
)
def test_airflow_invalid_export_rejects_instead_of_guessing(document: dict, message: str) -> None:
    """Duplicate identities and broken dependencies have actionable validation failures."""
    with pytest.raises(ValidationError, match=message):
        prepare_airflow(sources=SOURCES, request=request(JsonDocument.model_validate(document)))


def test_airflow_dataset_freshness_uses_latest_producer_across_consumers() -> None:
    """Later inlets and dataset collections cannot erase the newest producer timestamp."""
    uri = "postgres://warehouse.example/analytics.public.orders"
    document = JsonDocument(
        {
            "dags": [
                {
                    "dag_id": "sample",
                    "tasks": [
                        {"task_id": "new", "outlets": [uri]},
                        {"task_id": "old", "outlets": [uri]},
                        {"task_id": "consumer", "inlets": [uri]},
                    ],
                    "task_instances": [
                        {"task_id": "new", "state": "success", "end_date": "2026-10-27T02:00:00Z"},
                        {"task_id": "old", "state": "success", "end_date": "2026-10-26T02:00:00Z"},
                    ],
                }
            ],
            "datasets": [
                {
                    "uri": uri,
                    "producing_tasks": [
                        {"dag_id": "sample", "task_id": "new"},
                        {"dag_id": "sample", "task_id": "old"},
                    ],
                }
            ],
        }
    )
    table = next(
        item
        for item in prepare_airflow(sources=SOURCES, request=request(document)).snapshot.objects
        if item.asset_ref.asset_type == "table"
    )
    metadata = ExternalMetadata.model_validate(table.properties["integration"])
    assert metadata.details["last_success"] == "2026-10-27T02:00:00+00:00"


def test_airflow_latest_state_follows_logical_date_for_never_started_runs() -> None:
    """A queued run or upstream_failed instance in the newest run outranks an older success."""
    document = JsonDocument(
        {
            "dags": [
                {
                    "dag_id": "nightly",
                    "tasks": [{"task_id": "publish"}],
                    "dag_runs": [
                        {
                            "dag_run_id": "scheduled__2026-10-26",
                            "logical_date": "2026-10-26T02:30:00Z",
                            "start_date": "2026-10-27T02:30:00Z",
                            "end_date": "2026-10-27T02:47:00Z",
                            "state": "success",
                        },
                        {
                            "dag_run_id": "scheduled__2026-10-27",
                            "logical_date": "2026-10-27T02:30:00Z",
                            "state": "queued",
                        },
                    ],
                    "task_instances": [
                        {
                            "task_id": "publish",
                            "dag_run_id": "scheduled__2026-10-26",
                            "execution_date": "2026-10-26T02:30:00Z",
                            "start_date": "2026-10-27T02:45:00Z",
                            "end_date": "2026-10-27T02:47:00Z",
                            "state": "success",
                        },
                        {
                            "task_id": "publish",
                            "dag_run_id": "scheduled__2026-10-27",
                            "execution_date": "2026-10-27T02:30:00Z",
                            "state": "upstream_failed",
                        },
                    ],
                }
            ]
        }
    )
    objects = {
        item.asset_ref.asset_id: ExternalMetadata.model_validate(item.properties["integration"])
        for item in prepare_airflow(sources=SOURCES, request=request(document)).snapshot.objects
    }
    dag = objects["warehouse/dag/nightly"]
    task = objects["warehouse/dag/nightly/publish"]
    assert dag.details["state"] == "queued"
    assert dag.details["last_success"] == "2026-10-27T02:47:00+00:00"
    assert task.details["state"] == "upstream_failed"
    assert task.details["last_success"] == "2026-10-27T02:47:00+00:00"
