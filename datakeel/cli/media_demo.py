# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Generate, import and process a local multi-recording media demonstration."""

import argparse
from pathlib import Path
from typing import TYPE_CHECKING

from rich.console import Console

from datakeel.cli.parsers import CommandGroup
from datakeel.core.errors import ExecutionError
from datakeel.core.models import FileItem, JsonDocument
from datakeel.pipeline.media import media_pipeline
from datakeel.quality import build_report, score_quality
from datakeel.sample_media import generate_media
from datakeel.storage.database import Database, data_dir
from datakeel.storage.dataset_service import import_paths, list_files, list_versions
from datakeel.storage.task_queries import query_task
from datakeel.worker.queue import DatabaseQueue
from datakeel.worker.runner import run_worker

if TYPE_CHECKING:
    from pydantic import JsonValue


def register_parser(commands: CommandGroup) -> None:
    """Register a one-command generated recording demonstration."""
    command = commands.add_parser("demo-media")
    command.add_argument("--output", type=Path)
    # Repeatable: process your own local recordings instead of the generated ones.
    command.add_argument("--source", type=Path, action="append")


def run_demo(db: Database, recordings: list[Path] | None = None) -> JsonDocument:
    """Process lavfi sources, or given local recordings, through the durable queue."""
    if recordings:
        paths = recordings
        dataset = import_paths(db, "Local media recordings", paths)
    else:
        sources = generate_media(data_dir() / "media-demo")
        paths = [
            sources / "camera.mkv",
            sources / "camera-copy.mkv",
            sources / "external-microphone.wav",
        ]
        dataset = import_paths(
            db,
            "Generated multi-recording media",
            paths,
            {"license": "Apache-2.0", "creator": "Datakeel sample generator"},
        )
    task_id = DatabaseQueue(db).submit(
        dataset.id, f"media:{dataset.id}", media_pipeline(align=len(paths) > 1)
    )
    run_worker(db, once=True)
    task = query_task(db, task_id)
    if task.state != "COMPLETED":
        raise ExecutionError(task.error or task.state)
    version = list_versions(db, dataset.id)[-1]
    files = list_files(db, dataset.id, version.id)
    items = [FileItem(path="", **file.model_dump(exclude={"media"})) for file in files]
    quality = score_quality(items)
    report = build_report(dataset.model_dump(), quality)
    result: dict[str, JsonValue] = {
        "dataset_id": dataset.id,
        "task_id": task_id,
        "version_id": version.id,
        "state": task.state,
        # A completed task may still list recordings that failed (partial completion).
        "partial": task.partial,
        "failed_files": [failure.model_dump(mode="json") for failure in task.failed_files],
        "quality": quality.model_dump(mode="json"),
        "report": report.model_dump(mode="json"),
        "files": [file.model_dump(mode="json") for file in files],
    }
    return JsonDocument.model_validate(result)


def dispatch(db: Database, args: argparse.Namespace) -> None:
    """Print the measured report and optionally write its JSON representation."""
    result = run_demo(db, args.source)
    encoded = result.model_dump_json(indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded + "\n")
    Console().print(encoded, markup=False, highlight=False, soft_wrap=True)
