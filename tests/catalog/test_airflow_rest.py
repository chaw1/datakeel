# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Live Airflow REST v1 reads match the offline export through an injected fake scheduler."""

from __future__ import annotations

import base64
from pathlib import Path
from typing import TYPE_CHECKING

import httpx
import pytest
from pydantic import JsonValue, SecretStr

from datakeel.catalog.importers import airflow_rest
from datakeel.catalog.importers.airflow import prepare_airflow
from datakeel.catalog.importers.airflow_rest import (
    AirflowConnection,
    connection_from_settings,
    fetch_airflow_export,
)
from datakeel.catalog.metadata_service import import_airflow_api
from datakeel.core.errors import ExecutionError, ValidationError
from datakeel.core.metadata_imports import AirflowImportRequest, AirflowSource
from datakeel.core.models import JsonDocument
from datakeel.core.settings import Settings

if TYPE_CHECKING:
    from datakeel.storage.database import Database

FIXTURE = Path(__file__).parents[1] / "fixtures" / "metadata" / "airflow-v1.json"
BASE = "https://scheduler.example/airflow"
CREDENTIAL = "fixture-credential"
UNUSED_CREDENTIAL = "fixture-unused"


class FakeScheduler:
    """Serve documented v1 GET collections from the generated offline export."""

    def __init__(self, *, datasets: bool = True, status: int = 200) -> None:
        """Choose whether the dataset endpoint exists and a forced failure status."""
        self.export = JsonDocument.model_validate_json(FIXTURE.read_text()).root
        self.datasets = datasets
        self.status = status
        self.requests: list[httpx.Request] = []

    def _collection(self, key: str, dag: str, field: str) -> list[JsonValue]:
        group = self.export[key]
        assert isinstance(group, dict)
        entry = group[dag]
        assert isinstance(entry, dict)
        values = entry[field]
        assert isinstance(values, list)
        return values

    def _route(self, path: str, request: httpx.Request) -> JsonValue:
        parts = path.removeprefix("/airflow/api/v1/").split("/")
        if parts == ["dags"]:
            dags = self.export["dags"]
            assert isinstance(dags, list)
            offset = int(request.url.params["offset"])
            limit = int(request.url.params["limit"])
            return {"dags": dags[offset : offset + limit], "total_entries": len(dags)}
        if parts == ["datasets"]:
            return {"datasets": self.export["datasets"], "total_entries": 1}
        if parts[2] == "tasks":
            return {"tasks": self._collection("tasks", parts[1], "tasks")}
        if parts[2:] == ["dagRuns"]:
            return {"dag_runs": self._collection("dag_runs", parts[1], "dag_runs")}
        instances = self._collection("task_instances", parts[1], "task_instances")
        return {
            "task_instances": [
                item
                for item in instances
                if isinstance(item, dict) and item.get("dag_run_id") == parts[3]
            ]
        }

    def __call__(self, request: httpx.Request) -> httpx.Response:
        """Record each request and answer from the generated export."""
        self.requests.append(request)
        if self.status != 200:
            return httpx.Response(self.status, json={"title": "failure"})
        if request.url.path.endswith("/datasets") and not self.datasets:
            return httpx.Response(httpx.codes.NOT_FOUND, json={"title": "Not Found"})
        return httpx.Response(httpx.codes.OK, json=self._route(request.url.path, request))


def _connection(**updates: object) -> AirflowConnection:
    return AirflowConnection.model_validate({"base_url": BASE, **updates})


def _snapshot(document: JsonDocument) -> JsonDocument:
    batch = prepare_airflow(AirflowImportRequest(source_id="warehouse", document=document))
    return JsonDocument.model_validate(batch.snapshot.model_dump(mode="json"))


def test_live_export_when_paged_matches_offline_import(monkeypatch: pytest.MonkeyPatch) -> None:
    """Paged DAG reads, per-run task instances and datasets equal the offline document."""
    monkeypatch.setattr(airflow_rest, "_PAGE", 1)
    scheduler = FakeScheduler()
    document = fetch_airflow_export(_connection(), transport=httpx.MockTransport(scheduler))
    offline = JsonDocument.model_validate_json(FIXTURE.read_text())
    assert _snapshot(document) == _snapshot(offline)
    paths = [request.url.path for request in scheduler.requests]
    assert paths[0] == "/airflow/api/v1/dags"
    assert "/airflow/api/v1/dags/daily_orders/dagRuns/scheduled__first/taskInstances" in paths
    assert all(request.method == "GET" for request in scheduler.requests)


def test_live_export_when_token_configured_sends_bearer_only() -> None:
    """A configured token is the only credential and stays out of the export."""
    scheduler = FakeScheduler()
    document = fetch_airflow_export(
        _connection(token=CREDENTIAL, username="ignored", password=UNUSED_CREDENTIAL),
        transport=httpx.MockTransport(scheduler),
    )
    assert {request.headers["Authorization"] for request in scheduler.requests} == {
        f"Bearer {CREDENTIAL}"
    }
    assert CREDENTIAL not in document.model_dump_json()


def test_live_export_when_basic_auth_configured_sends_basic_credentials() -> None:
    """Airflow's default basic-auth backend receives the configured user and password."""
    scheduler = FakeScheduler()
    fetch_airflow_export(
        _connection(username="reader", password=CREDENTIAL),
        transport=httpx.MockTransport(scheduler),
    )
    expected = "Basic " + base64.b64encode(f"reader:{CREDENTIAL}".encode()).decode()
    assert {request.headers["Authorization"] for request in scheduler.requests} == {expected}


def test_live_export_when_dataset_endpoint_missing_still_imports_dags() -> None:
    """Schedulers older than dataset support return 404 and keep task metadata."""
    document = fetch_airflow_export(
        _connection(), transport=httpx.MockTransport(FakeScheduler(datasets=False))
    )
    assert document.root["datasets"] == []
    assert document.root["tasks"] != {}


def test_live_export_when_dag_filter_given_reads_only_selected_dags() -> None:
    """A DAG selection skips per-DAG requests for every other DAG."""
    scheduler = FakeScheduler()
    document = fetch_airflow_export(
        _connection(), ("other",), transport=httpx.MockTransport(scheduler)
    )
    assert document.root["dags"] == []
    assert not any("/dags/daily_orders/" in request.url.path for request in scheduler.requests)


@pytest.mark.parametrize("status", [401, 500])
def test_live_export_when_scheduler_rejects_raises_execution_error(status: int) -> None:
    """HTTP failures stop the import with the status and without partial publication."""
    with pytest.raises(ExecutionError, match=str(status)):
        fetch_airflow_export(
            _connection(), transport=httpx.MockTransport(FakeScheduler(status=status))
        )


def test_live_export_when_transport_fails_raises_execution_error() -> None:
    """Connection failures are reported as typed execution failures."""

    def refuse(request: httpx.Request) -> httpx.Response:
        reason = "refused"
        raise httpx.ConnectError(reason, request=request)

    with pytest.raises(ExecutionError, match="ConnectError"):
        fetch_airflow_export(_connection(), transport=httpx.MockTransport(refuse))


def test_live_export_when_body_is_not_json_raises_execution_error() -> None:
    """A proxy page or HTML error is not mistaken for an empty inventory."""
    transport = httpx.MockTransport(lambda _request: httpx.Response(200, text="<html>"))
    with pytest.raises(ExecutionError, match="invalid JSON"):
        fetch_airflow_export(_connection(), transport=transport)


def test_live_export_when_dag_lacks_identity_raises_execution_error() -> None:
    """Malformed DAG collections fail before any per-DAG request."""
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(200, json={"dags": [{"owners": []}], "total_entries": 1})
    )
    with pytest.raises(ExecutionError, match="dag_id"):
        fetch_airflow_export(_connection(), transport=transport)


def test_live_export_when_collection_field_is_not_array_raises_execution_error() -> None:
    """A changed response shape fails explicitly."""
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(200, json={"dags": {}, "total_entries": 1})
    )
    with pytest.raises(ExecutionError, match="array"):
        fetch_airflow_export(_connection(), transport=transport)


def test_live_export_when_required_endpoint_missing_raises_execution_error() -> None:
    """A wrong base URL produces a clear not-found failure rather than an empty import."""
    transport = httpx.MockTransport(lambda _request: httpx.Response(404, json={}))
    with pytest.raises(ExecutionError, match="not found"):
        fetch_airflow_export(_connection(), transport=transport)


def test_connection_when_settings_complete_reads_explicit_configuration() -> None:
    """Connection details come only from DATAKEEL_AIRFLOW_* settings."""
    connection = connection_from_settings(
        Settings(
            airflow_url=BASE,
            airflow_username="reader",
            airflow_password=SecretStr(CREDENTIAL),
            airflow_run_limit=3,
        )
    )
    assert connection.base_url == BASE
    assert connection.run_limit == 3


@pytest.mark.parametrize(
    "settings",
    [Settings(), Settings(airflow_url=BASE, airflow_username="reader")],
)
def test_connection_when_settings_incomplete_rejects(settings: Settings) -> None:
    """A missing URL or a user without password fails before any request."""
    with pytest.raises(ValidationError):
        connection_from_settings(settings)


def test_live_import_when_published_reports_new_then_unchanged(db: Database) -> None:
    """The live path publishes through the same incremental scope as offline imports."""
    transport = httpx.MockTransport(FakeScheduler())
    source = AirflowSource(source_id="warehouse")
    first = import_airflow_api(db, source, _connection(), transport)
    second = import_airflow_api(db, source, _connection(), transport)
    assert first.new == first.object_count
    assert second.unchanged == first.object_count
    assert second.event_id is None
