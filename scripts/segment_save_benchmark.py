# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Measure B8-style team saves with 100 native segments on an isolated local store."""

import argparse
import json
import math
import time
from collections.abc import Mapping
from pathlib import Path

from datakeel.actions.models import ActionContext, ApprovalDecision, ExecuteRequest
from datakeel.actions.service import approve_plan, execute_plan, prepare_action
from datakeel.core.models import JsonDocument, new_id
from datakeel.core.production_models import Project
from datakeel.storage.database import Database, data_dir
from datakeel.storage.dataset_service import import_paths, list_versions
from datakeel.storage.production_queries import list_tasks
from scripts.segment_media_fixtures import probe_sources, segment_sources

_WARMUPS = 3
_P95_LIMIT_MS = 200


def _run(db: Database, action: str, values: Mapping[str, object]) -> JsonDocument:
    body = JsonDocument.model_validate({"request_id": new_id(), **values})
    plan = prepare_action(db, action, body, ActionContext(actor="local"))
    if plan.requires_approval:
        approve_plan(db, plan.id, ApprovalDecision(approve=True, plan_digest=plan.plan_digest))
    result = execute_plan(db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest))
    if result.status != "SUCCEEDED" or result.receipt is None:
        message = f"Segment benchmark action failed: {action}"
        raise RuntimeError(message)
    return JsonDocument.model_validate(result.receipt.quality["details"])


def _setup(db: Database, media: Path) -> tuple[str, str, int]:
    labels = new_id()
    _run(
        db,
        "create_label_set",
        {"label_set_id": labels, "labels": [{"id": "speech", "name": "Speech"}]},
    )
    _run(db, "publish_label_set", {"label_set_id": labels, "version": 1})
    dataset = import_paths(db, "B8 segment source", segment_sources(media, 12_345, 1))
    version = list_versions(db, dataset.id)[0]
    durations = probe_sources(db, version.id)
    template = new_id()
    _run(
        db,
        "create_label_set",
        {
            "target": "template",
            "template": {"id": template, "name": "Segments", "annotation_type": "segment"},
        },
    )
    project = Project.model_validate(
        _run(
            db,
            "create_project",
            {
                "name": "B8 segments",
                "dataset_id": dataset.id,
                "version_id": version.id,
                "label_set_id": labels,
                "template_id": template,
                "workflow_tier": "team",
            },
        ).root
    )
    _run(db, "split_packages", {"project_id": project.id})
    task = list_tasks(db, project.id)[0]
    _run(db, "assign_tasks", {"task_ids": [task.id], "actor": "local"})
    return task.id, task.sample_id, durations[task.sample_id]


def _annotation(sample_id: str, duration: int, revision: int) -> dict[str, object]:
    return {
        "sample_id": sample_id,
        "annotator_id": "local",
        "attributes": {"revision": revision},
        "segments": [{"category": "speech", "start_ms": 0, "end_ms": 1000} for _ in range(100)],
        "media_duration_ms": duration,
    }


def main() -> None:
    """Run three warmups and thirty measured team saves, failing above the B8 limit."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    db = Database(f"sqlite:///{data_dir() / 'datakeel.db'}")
    try:
        db.migrate()
        task_id, sample_id, duration = _setup(db, args.output.parent / "benchmark-media")
        previous = None
        samples: list[float] = []
        for revision in range(33):
            started = time.perf_counter()
            result = _run(
                db,
                "save_revision",
                {
                    "task_id": task_id,
                    "previous_revision_id": previous,
                    "annotation": _annotation(sample_id, duration, revision),
                },
            )
            elapsed = (time.perf_counter() - started) * 1000
            previous = str(result.root["id"])
            if revision >= _WARMUPS:
                samples.append(elapsed)
        ordered = sorted(samples)
        p95 = ordered[math.ceil(len(ordered) * 0.95) - 1]
        report = {
            "scenario": "B8-segments",
            "database": "sqlite",
            "segmentsPerSave": 100,
            "warmups": 3,
            "samplesMs": samples,
            "p95Ms": p95,
            "limitMs": 200,
            "measurement": "save_revision prepare+execute, team assignment holder",
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        if p95 > _P95_LIMIT_MS:
            message = f"B8 segment save p95 {p95:.2f}ms exceeds 200ms"
            raise RuntimeError(message)
    finally:
        db.engine.dispose()


if __name__ == "__main__":
    main()
