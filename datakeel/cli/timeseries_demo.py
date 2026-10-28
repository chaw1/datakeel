# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Import generated sensors and publish durable profiles through existing controlled actions."""

from pathlib import Path

from rich.console import Console

from datakeel.actions.catalog_parameters import ImportCatalogParams
from datakeel.actions.models import ExecuteRequest
from datakeel.actions.parameters import PipelineParams
from datakeel.actions.service import execute_plan, prepare_action
from datakeel.cli.parsers import CommandGroup
from datakeel.core.catalog_models import CatalogImportRequest
from datakeel.core.errors import ExecutionError
from datakeel.core.models import BoundaryModel, JsonDocument
from datakeel.operators.timeseries.models import ColumnRange, UnitDeclaration
from datakeel.pipeline.tabular import timeseries_pipeline
from datakeel.quality import build_report
from datakeel.sample_timeseries import generate_sensor_samples
from datakeel.storage.database import Database, data_dir
from datakeel.storage.dataset_service import import_paths
from datakeel.storage.governance_service import get_quality
from datakeel.storage.task_queries import query_task
from datakeel.worker.runner import run_worker


class TimeseriesDemoResult(BoundaryModel):
    """Link the durable worker, controlled catalog publication and local report artifacts."""

    dataset_id: str
    task_id: str
    state: str
    catalog_action_id: str
    catalog_source: str
    quality_score: float
    report_path: Path
    evidence_path: Path


def _execute(db: Database, action: str, params: BoundaryModel) -> tuple[str, str | None]:
    plan = prepare_action(db, action, JsonDocument.model_validate(params.model_dump(mode="json")))
    if plan.requires_approval:
        msg = "The generated local sensor demo must remain within automatic action limits"
        raise ExecutionError(msg)
    run = execute_plan(db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest))
    if run.status not in {"SUCCEEDED", "QUEUED", "RUNNING"}:
        msg = f"Sensor demo action failed: {run.status}"
        raise ExecutionError(msg)
    return run.id, run.task_id


def run_timeseries_demo(db: Database, output: Path) -> TimeseriesDemoResult:
    """Run the complete offline sensor chain and persist the same report used by the API."""
    samples = generate_sensor_samples(output / "sources")
    dataset = import_paths(
        db,
        "Smart kitchen · generated sensor week",
        list(samples.paths),
        {"description": "Three fictional kitchen devices sampled for one week", "generated": True},
    )
    pipeline = timeseries_pipeline(
        interval_ms=samples.interval_ms,
        values=("temperature", "fan_speed"),
        ranges=(ColumnRange(column="temperature", minimum=-20, maximum=150),),
        units=(UnitDeclaration(column="gas_flow", unit="L/min", minimum=0, maximum=10),),
    )
    _, task_id = _execute(
        db, "run_pipeline", PipelineParams(dataset_id=dataset.id, pipeline=pipeline)
    )
    if task_id is None:
        msg = "Sensor pipeline did not schedule a task"
        raise ExecutionError(msg)
    run_worker(db, once=True)
    task = query_task(db, task_id)
    if task.state != "COMPLETED":
        raise ExecutionError(task.error or "Sensor pipeline did not complete")
    source = f"sensor-{dataset.id}"
    action_id, _ = _execute(
        db,
        "import_catalog",
        ImportCatalogParams(
            request=CatalogImportRequest(
                source_id=source,
                name="Generated smart kitchen sensors",
                files=tuple(map(str, samples.paths)),
            )
        ),
    )
    quality = get_quality(db, dataset.id)
    report = build_report(dataset.model_dump(), quality)
    output.mkdir(parents=True, exist_ok=True)
    report_path, evidence_path = output / "report.md", output / "quality.json"
    report_path.write_text(report.body + "\n", encoding="utf-8")
    evidence_path.write_text(quality.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return TimeseriesDemoResult(
        dataset_id=dataset.id,
        task_id=task_id,
        state=task.state,
        catalog_action_id=action_id,
        catalog_source=source,
        quality_score=quality.total,
        report_path=report_path,
        evidence_path=evidence_path,
    )


def demo(db: Database, output: Path | None = None) -> None:
    """Print durable identities for a one-command generated demonstration."""
    result = run_timeseries_demo(db, output or data_dir() / "sensor-demo")
    Console().print(result.model_dump_json(), markup=False, soft_wrap=True)


def register_parser(commands: CommandGroup) -> None:
    """Register the isolated, one-shot sensor demonstration grammar."""
    command = commands.add_parser("timeseries-demo")
    command.add_argument("--output", type=Path)
