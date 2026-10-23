# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Repeatable local HTTP checks and real two-process worker verification."""

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import jsonschema
from rich.console import Console
from sqlalchemy import select

from datakeel.http import Client
from datakeel.storage.database import Database, ShardRow, TaskRow, data_dir
from datakeel.storage.datasets import import_dataset
from datakeel.worker.queue import DatabaseQueue

EXPECTED_DEMO_FILES = 400
MINIMUM_VERSIONS = 2
EXPECTED_OPERATORS = 11
QUALITY_DIMENSIONS = 5
REPORT_CHAPTERS = 6


def check(description: str, *, condition: bool) -> None:
    """Fail acceptance explicitly even when Python assertions are disabled."""
    if not condition:
        raise RuntimeError(description)


def verify_http(base: str) -> dict[str, Any]:
    """Exercise the complete phase-one HTTP contract on generated local data."""
    with Client(base_url=base, timeout=10) as client:
        datasets = client.get("/api/datasets").raise_for_status().json()
        dataset = next(item for item in datasets if item["name"].startswith("Field notes"))
        identifier = dataset["id"]
        root = f"/api/datasets/{identifier}"
        files = client.get(root + "/files").raise_for_status().json()
        check(
            'Acceptance failed: len(files) == dataset["file_count"] == EXPECTED_DEMO_FILES',
            condition=bool(len(files) == dataset["file_count"] == EXPECTED_DEMO_FILES),
        )
        versions = client.get(root + "/versions").raise_for_status().json()
        check(
            "Acceptance failed: len(versions) >= MINIMUM_VERSIONS",
            condition=bool(len(versions) >= MINIMUM_VERSIONS),
        )
        task = next(
            item for item in client.get("/api/tasks").json() if item["dataset_id"] == identifier
        )
        check(str(task), condition=bool(task["state"] == "COMPLETED"))
        artifacts = client.get(f"/api/tasks/{task['id']}/artifacts").raise_for_status().json()
        downloaded = client.get(root + f"/files/{artifacts[0]['id']}/download").raise_for_status()
        check("Acceptance failed: downloaded.content", condition=bool(downloaded.content))
        lineage = (
            client.get("/api/lineage/graph", params={"asset": identifier}).raise_for_status().json()
        )
        operators = {
            event["operator"] for event in lineage["events"] if event["source_module"] == "pipeline"
        }
        check(str(operators), condition=bool(len(operators) == EXPECTED_OPERATORS))
        replay = (
            client.post("/api/lineage/events", json=lineage["events"][0]).raise_for_status().json()
        )
        check(
            'Acceptance failed: replay == {"inserted": False}',
            condition=bool(replay == {"inserted": False}),
        )
        quality, adjusted, report = _verify_quality(client, root)
        events, croissant = _verify_exports(client, identifier)
        return {
            "dataset_id": identifier,
            "source_files": len(files),
            "versions": len(versions),
            "task_state": task["state"],
            "artifacts": len(artifacts),
            "operator_events": len(operators),
            "lineage_edges": len(lineage["edges"]),
            "quality": quality["total"],
            "adjusted_quality": adjusted["total"],
            "report_chapters": len(report["chapters"]),
            "official_schema_valid_events": len(events),
            "croissant_files": len(croissant["distribution"]),
        }


def _verify_quality(
    client: Client, root: str
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    quality = client.get(root + "/quality").raise_for_status().json()
    check(
        'Acceptance failed: len(quality["dimensions"]) == QUALITY_DIMENSIONS',
        condition=bool(len(quality["dimensions"]) == QUALITY_DIMENSIONS),
    )
    adjusted = (
        client.put(root + "/quality/config", json={"min_size_bytes": 999999})
        .raise_for_status()
        .json()
    )
    check(
        'Acceptance failed: adjusted["total"] != quality["total"]',
        condition=bool(adjusted["total"] != quality["total"]),
    )
    client.put(root + "/quality/config", json={}).raise_for_status()
    report = client.get(root + "/report").raise_for_status().json()
    check(
        'Acceptance failed: len(report["chapters"]) == REPORT_CHAPTERS',
        condition=bool(len(report["chapters"]) == REPORT_CHAPTERS),
    )
    return quality, adjusted, report


def _verify_exports(client: Client, identifier: str) -> tuple[list[Any], dict[str, Any]]:
    events = (
        client.get("/api/export", params={"format": "openlineage", "dataset_id": identifier})
        .raise_for_status()
        .json()
    )
    schema = json.loads(Path("tests/fixtures/openlineage-2-0-2.json").read_text())
    for event in events:
        jsonschema.validate(event, schema, format_checker=jsonschema.FormatChecker())
    croissant = (
        client.get("/api/export", params={"format": "croissant", "dataset_id": identifier})
        .raise_for_status()
        .json()
    )
    check(
        'Acceptance failed: {"@context", "distribution", "recordSet"} <= croissant.keys()',
        condition=bool({"@context", "distribution", "recordSet"} <= croissant.keys()),
    )
    check(
        'Acceptance failed: len(croissant["distribution"]) == EXPECTED_DEMO_FILES',
        condition=bool(len(croissant["distribution"]) == EXPECTED_DEMO_FILES),
    )
    return events, croissant


def verify_workers() -> dict[str, Any]:
    """Verify isolated local PostgreSQL shard claims in two actual workers."""
    db = Database()
    check(
        "Use a new local PostgreSQL instance",
        condition=bool(db.engine.url.host in ("localhost", "127.0.0.1")),
    )
    db.migrate()
    directory = data_dir() / "parallel-inputs"
    directory.mkdir(parents=True, exist_ok=True)
    paths = []
    for index in range(80):
        path = directory / f"observation-{index}.txt"
        path.write_text(
            f"Observation {index}: generated two-worker verification sample {index * 7919}."
        )
        paths.append(path)
    with db.session() as session:
        dataset = import_dataset(session, "two-worker-verification", paths)
        session.commit()
        identifier = dataset.id
    task_id = DatabaseQueue(db).submit(identifier, f"parallel:{identifier}", shards=8)
    processes = [
        subprocess.Popen(
            [sys.executable, "-m", "datakeel.cli", "worker", "--once"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=dict(os.environ),
        )
        for _ in range(2)
    ]
    outputs = []
    try:
        for process in processes:
            stdout, stderr = process.communicate(timeout=60)
            check(str(stderr), condition=bool(process.returncode == 0))
            outputs.append(stdout + stderr)
    finally:
        for process in processes:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=10)
    return _worker_result(db, task_id, outputs)


def _worker_result(db: Database, task_id: str, outputs: list[str]) -> dict[str, Any]:
    with db.session() as session:
        task = session.get(TaskRow, task_id)
        shards = list(session.scalars(select(ShardRow).where(ShardRow.task_id == task_id)))
        check("Acceptance failed: task is not None", condition=bool(task is not None))
        check(
            'Acceptance failed: task.state == "COMPLETED"',
            condition=bool(task.state == "COMPLETED"),
        )
        check(
            "Each shard must complete exactly one attempt",
            condition=bool(
                all(shard.attempts == 1 and shard.state == "COMPLETED" for shard in shards)
            ),
        )
        check(str(outputs), condition=bool(all("committed" in output for output in outputs)))
        return {
            "task_id": task_id,
            "state": task.state,
            "shards": len(shards),
            "attempts": [shard.attempts for shard in shards],
            "worker_outputs": outputs,
        }


def main() -> None:
    """Run requested acceptance checks and emit machine-readable evidence."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url")
    parser.add_argument("--workers", action="store_true")
    args = parser.parse_args()
    started = time.monotonic()
    result = {}
    if args.base_url:
        result["http"] = verify_http(args.base_url)
    if args.workers:
        result["workers"] = verify_workers()
    result["elapsed_seconds"] = round(time.monotonic() - started, 3)
    Console().print(json.dumps(result, indent=2, ensure_ascii=False), markup=False, soft_wrap=True)


if __name__ == "__main__":
    main()
