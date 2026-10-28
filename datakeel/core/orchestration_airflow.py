# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Offline Airflow REST v1 response collections and documented export additions."""

from pydantic import AwareDatetime, ConfigDict, Field, JsonValue

from datakeel.core.models import BoundaryModel


class AirflowResponse(BoundaryModel):
    """Ignore unused Airflow API response fields to tolerate minor v1 additions."""

    model_config = ConfigDict(extra="ignore", frozen=True)


class AirflowRun(AirflowResponse):
    """Retain DAG-run or task-instance state and authoritative timestamps."""

    dag_run_id: str = ""
    task_id: str | None = None
    state: str | None = None
    logical_date: AwareDatetime | None = None
    execution_date: AwareDatetime | None = None
    start_date: AwareDatetime | None = None
    end_date: AwareDatetime | None = None


class AirflowDatasetReference(AirflowResponse):
    """Identify producing tasks and consuming DAGs from DatasetCollection."""

    dag_id: str
    task_id: str | None = None


class AirflowDataset(AirflowResponse):
    """Retain standard dataset URIs and v1 scheduler dependency references."""

    uri: str = Field(min_length=1)
    producing_tasks: tuple[AirflowDatasetReference, ...] = ()
    consuming_dags: tuple[AirflowDatasetReference, ...] = ()


class AirflowTask(AirflowResponse):
    """Read v1 Task plus optional offline-export inlets and outlets."""

    task_id: str = Field(min_length=1)
    task_display_name: str | None = None
    owner: str | None = None
    doc_md: str | None = None
    downstream_task_ids: tuple[str, ...] = ()
    inlets: tuple[str | AirflowDataset, ...] = ()
    outlets: tuple[str | AirflowDataset, ...] = ()


class AirflowTag(AirflowResponse):
    """Read one named v1 DAG tag."""

    name: str


class AirflowDag(AirflowResponse):
    """Read DAG details with optional nested offline endpoint collections."""

    dag_id: str = Field(min_length=1)
    dag_display_name: str | None = None
    owners: tuple[str, ...] = ()
    description: str | None = None
    schedule_interval: JsonValue = None
    timetable_description: str | None = None
    is_paused: bool | None = None
    is_active: bool | None = None
    tags: tuple[str | AirflowTag, ...] | None = ()
    tasks: tuple[AirflowTask, ...] = ()
    dag_runs: tuple[AirflowRun, ...] = ()
    task_instances: tuple[AirflowRun, ...] = ()


class AirflowTaskCollection(AirflowResponse):
    """Read GET /dags/{dag_id}/tasks output."""

    tasks: tuple[AirflowTask, ...] = ()


class AirflowRunCollection(AirflowResponse):
    """Read GET /dags/{dag_id}/dagRuns output."""

    dag_runs: tuple[AirflowRun, ...] = ()


class AirflowTaskInstanceCollection(AirflowResponse):
    """Read GET /dags/{dag_id}/dagRuns/{dag_run_id}/taskInstances output."""

    task_instances: tuple[AirflowRun, ...] = ()


class AirflowExport(AirflowResponse):
    """Combine independently exported v1 responses, keyed by their DAG identity.

    The dags and datasets arrays preserve their official collection shape. The
    task/run collections are keyed by DAG ID because they have separate v1 URLs.
    Equivalent nested arrays on each DAG are supported for portable exports.
    """

    dags: tuple[AirflowDag, ...]
    datasets: tuple[AirflowDataset, ...] = ()
    tasks: dict[str, AirflowTaskCollection] = Field(default_factory=dict)
    dag_runs: dict[str, AirflowRunCollection] = Field(default_factory=dict)
    task_instances: dict[str, AirflowTaskInstanceCollection] = Field(default_factory=dict)
