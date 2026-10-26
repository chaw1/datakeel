# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Seed a generated demo and supervise the local API/worker processes."""

import argparse
import json
import signal
import subprocess
import sys
import time
from contextlib import suppress
from types import FrameType

import httpx
from rich.console import Console

from datakeel.cli.enterprise import seed_enterprise_demo
from datakeel.cli.evidence import seed_evidence_demo
from datakeel.cli.image_kg_demo import seed_image_kg_demo
from datakeel.cli.kg_demo import check_demo, demo_reports, seed_kg_demo
from datakeel.core.errors import ExecutionError
from datakeel.core.standard_history_models import StandardsReport
from datakeel.harness.enterprise_kg import (
    check_enterprise_extraction,
    import_enterprise_documents,
    schedule_enterprise_extraction,
)
from datakeel.harness.standard_cases import seed_standard_demo
from datakeel.http import Client
from datakeel.sample import generate_samples
from datakeel.storage.database import Database, data_dir
from datakeel.storage.dataset_service import import_paths, list_datasets
from datakeel.storage.evidence_runs import extraction_report
from datakeel.storage.task_queries import query_task
from datakeel.worker.queue import DatabaseQueue
from datakeel.worker.runner import run_worker

STARTUP_TIMEOUT = 60
DEMO_NAME = "Field notes · generated demo"
console = Console(highlight=False)


def seed_demo(db: Database) -> tuple[str, str]:
    """Reuse or generate the fixture dataset and its idempotent pipeline task."""
    dataset = next((value for value in list_datasets(db) if value.name == DEMO_NAME), None)
    if dataset is None:
        dataset = import_paths(
            db,
            DEMO_NAME,
            generate_samples(data_dir() / "sample-data"),
            {
                "description": "200 generated images and 200 generated text observations.",
                "license": "https://spdx.org/licenses/Apache-2.0.html",
                "creator": "Datakeel sample generator",
            },
        )
    return dataset.id, DatabaseQueue(db).submit(dataset.id, f"demo:{dataset.id}:v1")


def _check_task(db: Database, task_id: str) -> bool:
    task = query_task(db, task_id)
    if task.state == "FAILED":
        raise ExecutionError(task.error or task.state)
    return task.state == "COMPLETED"


def _wait_ready(
    db: Database,
    task_id: str,
    base: str,
    children: list[subprocess.Popen[bytes]],
    started: float,
    evidence_task_id: str | None = None,
) -> None:
    while time.monotonic() - started < STARTUP_TIMEOUT:
        if any(child.poll() is not None for child in children):
            msg = "API or worker exited during startup"
            raise ExecutionError(msg)
        complete = _check_task(db, task_id)
        if evidence_task_id is not None:
            complete = _check_task(db, evidence_task_id) and complete
        if complete:
            with suppress(httpx.TransportError), Client(base, timeout=1) as client:
                if client.get("/api/health").is_success:
                    return
        time.sleep(0.15)
    msg = "Demo did not become ready within 60 seconds"
    raise ExecutionError(msg)


def _stop(children: list[subprocess.Popen[bytes]]) -> None:
    for child in children:
        if child.poll() is None:
            child.terminate()
    for child in children:
        try:
            child.wait(timeout=10)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait()


def _interrupt(_signum: int, _frame: FrameType | None) -> None:
    raise KeyboardInterrupt


def _serve(
    db: Database,
    task_id: str,
    args: argparse.Namespace,
    started: float,
    evidence_task_id: str | None = None,
) -> None:
    children: list[subprocess.Popen[bytes]] = []
    previous = signal.signal(signal.SIGTERM, _interrupt)
    try:
        children.append(subprocess.Popen([sys.executable, "-m", "datakeel.cli", "worker"]))
        children.append(
            subprocess.Popen(  # noqa: S603  # Fixed Python module; bind values are argv, no shell.
                [
                    sys.executable,
                    "-m",
                    "datakeel.cli",
                    "api",
                    "--host",
                    args.host,
                    "--port",
                    str(args.port),
                ]
            )
        )
        base = f"http://{args.host}:{args.port}"
        console.print(f"API: {base}/api/docs\nPage: {base}/", markup=False)
        _wait_ready(db, task_id, base, children, time.monotonic(), evidence_task_id)
        elapsed = time.monotonic() - started
        console.print(f"Demo COMPLETED: 400 source files in {elapsed:.2f}s. Press Ctrl+C to stop.")
        if evidence_task_id is not None:
            console.print(extraction_report(db, evidence_task_id).model_dump_json(), markup=False)
        while all(child.poll() is None for child in children):
            time.sleep(0.5)
        msg = "API or worker exited"
        raise ExecutionError(msg)
    except KeyboardInterrupt:
        console.print("\nStopping demo.")
    finally:
        signal.signal(signal.SIGTERM, previous)
        _stop(children)


def _check_processed(db: Database, task_id: str, evidence_task_id: str | None) -> None:
    if not _check_task(db, task_id):
        msg = "Demo task did not complete"
        raise ExecutionError(msg)
    if evidence_task_id and not _check_task(db, evidence_task_id):
        msg = "Evidence demo task did not complete"
        raise ExecutionError(msg)


def _seed_standards(db: Database, *, legacy_only: bool) -> StandardsReport | None:
    return None if legacy_only else seed_standard_demo(db, data_dir() / "standards-demo")


def demo(args: argparse.Namespace) -> None:
    """Run the complete local demonstration without external services."""
    started = time.monotonic()
    db = Database()
    db.migrate()
    dataset_id, task_id = seed_demo(db)
    evidence = None if getattr(args, "legacy_only", False) else seed_evidence_demo(db)
    enterprise = None if getattr(args, "legacy_only", False) else seed_enterprise_demo(db)
    graph = None if getattr(args, "legacy_only", False) else seed_kg_demo(db)
    image_graph = None if getattr(args, "legacy_only", False) else seed_image_kg_demo(db)
    standards = _seed_standards(db, legacy_only=getattr(args, "legacy_only", False))
    documents = (
        import_enterprise_documents(db, data_dir() / "enterprise-documents") if graph else None
    )
    document_task = schedule_enterprise_extraction(db, documents) if documents else None
    if not args.once:
        if enterprise is not None:
            console.print(enterprise.model_dump_json(), markup=False, soft_wrap=True)
        _serve(db, task_id, args, started, evidence[1] if evidence else None)
        return
    run_worker(db, once=True)
    _check_processed(db, task_id, evidence[1] if evidence else None)
    if graph:
        check_demo(db, graph)
    if image_graph:
        check_demo(db, image_graph)
    if documents and document_task:
        check_enterprise_extraction(db, documents, document_task)
    console.print(
        json.dumps(
            {
                "dataset_id": dataset_id,
                "task_id": task_id,
                "state": "COMPLETED",
                "elapsed_seconds": round(time.monotonic() - started, 3),
                "enterprise": enterprise.model_dump(mode="json") if enterprise else None,
                "standards": standards.coverage.model_dump(mode="json") if standards else None,
                "enterprise_documents": documents.model_dump(mode="json") if documents else None,
                "knowledge_graph": [run.model_dump(mode="json") for run in demo_reports(db, graph)]
                if graph
                else None,
                "image_knowledge_graph": [
                    run.model_dump(mode="json") for run in demo_reports(db, image_graph)
                ]
                if image_graph
                else None,
                "evidence": {
                    "dataset_id": evidence[0],
                    **extraction_report(db, evidence[1]).model_dump(mode="json"),
                }
                if evidence
                else None,
            }
        ),
        markup=False,
        soft_wrap=True,
    )
