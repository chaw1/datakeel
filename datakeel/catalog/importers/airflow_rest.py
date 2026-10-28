# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Read the Airflow stable REST API v1 into the same offline export document.

Only documented v1 GET endpoints are used: DAG and dataset collections are paged
with ``limit``/``offset`` and ``total_entries``; tasks come from one DAG endpoint;
the newest DAG runs and their task instances provide state and freshness.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from urllib.parse import quote

import httpx
from pydantic import Field, JsonValue, SecretStr

from datakeel.core.errors import ExecutionError, ValidationError
from datakeel.core.models import BoundaryModel, JsonDocument

if TYPE_CHECKING:
    from datakeel.core.settings import Settings

_PAGE = 100
_NOT_FOUND = 404


class AirflowConnection(BoundaryModel):
    """Configured scheduler address and optional credential, never read from artifacts."""

    base_url: str = Field(min_length=1)
    token: SecretStr | None = None
    username: str | None = None
    password: SecretStr | None = None
    timeout: float = Field(default=30, gt=0, le=120)
    run_limit: int = Field(default=10, ge=1, le=100)


def connection_from_settings(settings: Settings) -> AirflowConnection:
    """Require the explicit DATAKEEL_AIRFLOW_URL configuration before any request."""
    if not settings.airflow_url:
        msg = "Live Airflow import requires DATAKEEL_AIRFLOW_URL"
        raise ValidationError(msg)
    if settings.airflow_username and settings.airflow_password is None:
        msg = "DATAKEEL_AIRFLOW_USERNAME requires DATAKEEL_AIRFLOW_PASSWORD"
        raise ValidationError(msg)
    return AirflowConnection(
        base_url=settings.airflow_url,
        token=settings.airflow_token,
        username=settings.airflow_username,
        password=settings.airflow_password,
        timeout=settings.airflow_timeout,
        run_limit=settings.airflow_run_limit,
    )


def _client(connection: AirflowConnection, transport: httpx.BaseTransport | None) -> httpx.Client:
    headers = {"Accept": "application/json"}
    auth: httpx.BasicAuth | None = None
    if connection.token is not None:
        headers["Authorization"] = f"Bearer {connection.token.get_secret_value()}"
    elif connection.username and connection.password is not None:
        auth = httpx.BasicAuth(connection.username, connection.password.get_secret_value())
    return httpx.Client(
        base_url=connection.base_url.rstrip("/") + "/api/v1/",
        headers=headers,
        auth=auth,
        timeout=connection.timeout,
        transport=transport,
        trust_env=False,
        follow_redirects=False,
    )


def _get(
    client: httpx.Client, path: str, params: dict[str, str | int] | None = None
) -> dict[str, JsonValue] | None:
    try:
        response = client.get(path, params=params)
    except httpx.HTTPError as error:
        msg = f"Airflow request failed: {type(error).__name__}"
        raise ExecutionError(msg) from error
    if response.status_code == _NOT_FOUND:
        return None
    if response.is_error:
        msg = f"Airflow API returned HTTP {response.status_code} for {path}"
        raise ExecutionError(msg)
    try:
        body = JsonDocument.model_validate_json(response.content).root
    except ValueError as error:
        msg = f"Airflow API returned invalid JSON for {path}"
        raise ExecutionError(msg) from error
    return body


def _required(
    client: httpx.Client, path: str, params: dict[str, str | int] | None = None
) -> dict[str, JsonValue]:
    body = _get(client, path, params)
    if body is None:
        msg = f"Airflow API endpoint not found: {path}"
        raise ExecutionError(msg)
    return body


def _items(body: dict[str, JsonValue], key: str) -> list[JsonValue]:
    values = body.get(key, [])
    if not isinstance(values, list):
        msg = f"Airflow API field {key} must be an array"
        raise ExecutionError(msg)
    return values


def _paged(client: httpx.Client, path: str, key: str, *, optional: bool = False) -> list[JsonValue]:
    result: list[JsonValue] = []
    while True:
        params: dict[str, str | int] = {"limit": _PAGE, "offset": len(result)}
        body = _get(client, path, params) if optional else _required(client, path, params)
        if body is None:
            return result
        page = _items(body, key)
        result.extend(page)
        total = body.get("total_entries")
        if not page or not isinstance(total, int) or len(result) >= total:
            return result


def _dag_id(value: JsonValue) -> str:
    identity = value.get("dag_id") if isinstance(value, dict) else None
    if not isinstance(identity, str) or not identity:
        msg = "Airflow DAG response lacks dag_id"
        raise ExecutionError(msg)
    return identity


def _runs(client: httpx.Client, dag: str, limit: int) -> tuple[list[JsonValue], list[JsonValue]]:
    body = _required(client, f"dags/{dag}/dagRuns", {"limit": limit, "order_by": "-execution_date"})
    runs = _items(body, "dag_runs")
    instances: list[JsonValue] = []
    for run in runs:
        identity = run.get("dag_run_id") if isinstance(run, dict) else None
        if isinstance(identity, str):
            path = f"dags/{dag}/dagRuns/{quote(identity, safe='')}/taskInstances"
            instances.extend(_items(_required(client, path), "task_instances"))
    return runs, instances


def fetch_airflow_export(
    connection: AirflowConnection,
    dag_ids: tuple[str, ...] = (),
    transport: httpx.BaseTransport | None = None,
) -> JsonDocument:
    """Collect DAGs, tasks, recent runs, task instances and datasets as one export."""
    with _client(connection, transport) as client:
        dags = [
            dag for dag in _paged(client, "dags", "dags") if not dag_ids or _dag_id(dag) in dag_ids
        ]
        tasks: dict[str, JsonValue] = {}
        runs: dict[str, JsonValue] = {}
        instances: dict[str, JsonValue] = {}
        for dag in dags:
            identity = _dag_id(dag)
            quoted = quote(identity, safe="")
            tasks[identity] = {"tasks": _items(_required(client, f"dags/{quoted}/tasks"), "tasks")}
            dag_runs, task_instances = _runs(client, quoted, connection.run_limit)
            runs[identity] = {"dag_runs": dag_runs}
            instances[identity] = {"task_instances": task_instances}
        datasets = _paged(client, "datasets", "datasets", optional=True)
    return JsonDocument(
        {
            "dags": dags,
            "tasks": tasks,
            "dag_runs": runs,
            "task_instances": instances,
            "datasets": datasets,
        }
    )
