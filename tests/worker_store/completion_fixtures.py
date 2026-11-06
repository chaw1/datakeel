# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Real generated jobs for each completion adapter, without invoking model providers."""

from pathlib import Path

from datakeel.actions.models import ExecuteRequest
from datakeel.actions.service import execute_plan, prepare_action
from datakeel.core.datasheet_execution import DatasheetCompletion, DatasheetFence
from datakeel.core.datasheet_models import DatasheetDocument
from datakeel.core.dq_models import DqResult
from datakeel.core.dq_monitor import DqCompletion
from datakeel.core.kg_execution import KGCompletion
from datakeel.core.kg_product import ProductExtraction
from datakeel.core.models import JsonDocument
from datakeel.datasheets.templates import build_template
from datakeel.persistence.task_queue import DatabaseQueue
from datakeel.storage.database import Database
from datakeel.storage.datasheet_jobs import job_input
from datakeel.storage.kg_store import get_job
from datakeel.worker_store.completion import CompletionPayload
from datakeel.worker_store.task_queue import Lease
from tests.dq_support import generated_rule, save_rule
from tests.kg.integration_helpers import prepare_graph, text_dataset


def enqueue(
    db: Database, directory: Path, kind: str
) -> tuple[DatabaseQueue, Lease, CompletionPayload]:
    """Schedule through real actions, then prepare only a typed deterministic product."""
    dataset = text_dataset(db, directory, ("Acme uses Widget.",))
    if kind == "kg":
        plan = prepare_graph(db, dataset)
    elif kind == "dq":
        rule = generated_rule(db, directory)
        save_rule(db, rule)
        plan = prepare_action(db, "run_quality_rule", JsonDocument({"rule_id": rule.id}))
    else:
        action = "generate_datasheet" if kind == "datasheet" else "run_pipeline"
        params = (
            {"dataset_id": dataset.dataset_id, "version_id": dataset.version_id, "mode": "model"}
            if kind == "datasheet"
            else {"dataset_id": dataset.dataset_id}
        )
        plan = prepare_action(db, action, JsonDocument(params))
    execute_plan(db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest))
    queue = DatabaseQueue(db, lease_seconds=0.01, max_attempts=1)
    queue.relay()
    lease = queue.claim()
    assert lease is not None
    return queue, lease, product(db, lease, kind)


def product(db: Database, lease: Lease, kind: str) -> CompletionPayload:
    """Restore exact frozen job inputs for successful publication tests."""
    if kind == "kg":
        run = get_job(db, lease.kg_run_id or "").run.model_copy(update={"status": "completed"})
        return KGCompletion(run=run, products=ProductExtraction())
    if kind == "dq":
        return DqCompletion(
            run_id=lease.dq_run_id or "",
            result=DqResult(rule_id="orders-positive", status="passed"),
        )
    if kind == "datasheet":
        job, prepared = job_input(
            db,
            lease.datasheet_job_id or "",
            DatasheetFence(task_id=lease.task_id, shard_id=lease.shard_id, owner=lease.owner),
        )
        return DatasheetCompletion(
            job_id=job.id,
            document=DatasheetDocument(
                id=job.id,
                dataset_id=job.dataset_id,
                version_id=job.version_id,
                facts=prepared.facts,
                language=job.language,
                mode="model",
                sections=build_template(prepared.facts, job.language).sections,
            ),
        )
    return ()
