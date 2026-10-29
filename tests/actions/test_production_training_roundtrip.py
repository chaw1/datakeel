# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Finalized production versions round-trip through training exports and prediction imports."""

from __future__ import annotations

import io
import json
import tarfile
from pathlib import PurePosixPath
from typing import TYPE_CHECKING

import pytest
import yaml
from PIL import Image
from sqlalchemy import select

from datakeel.actions import service
from datakeel.actions.models import ActionContext, ApprovalDecision, ExecuteRequest
from datakeel.core.annotation_models import AnnotationBatch, AnnotationBox
from datakeel.core.models import JsonDocument
from datakeel.core.production_models import Project
from datakeel.core.training_models import SplitRequest
from datakeel.storage.annotation_rows import AnnotationBatchRow
from datakeel.storage.database import data_dir
from datakeel.storage.production_queries import list_revisions, list_tasks
from datakeel.storage.training_store import create_split
from tests.production_flow_support import action_payload, personal_flow

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from datakeel.storage.database import Database

_PIXEL_TOLERANCE = 1e-9


class _Runner:
    def __init__(self, db: Database) -> None:
        self.db = db

    def __call__(
        self, action: str, values: Mapping[str, object], actor: str = "local"
    ) -> JsonDocument:
        plan = service.prepare_action(
            self.db, action, action_payload(action, values), ActionContext(actor=actor)
        )
        if plan.requires_approval:
            service.approve_plan(
                self.db,
                plan.id,
                ApprovalDecision(approve=True, plan_digest=plan.plan_digest, actor=actor),
            )
        run = service.execute_plan(
            self.db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest, actor=actor)
        )
        assert run.status == "SUCCEEDED"
        assert run.receipt is not None
        return JsonDocument.model_validate(run.receipt.quality.get("details", {}))


def _finalized_boxes(db: Database, version_id: str) -> dict[str, tuple[AnnotationBox, ...]]:
    with db.session() as session:
        row = session.scalar(
            select(AnnotationBatchRow).where(AnnotationBatchRow.version_id == version_id)
        )
        assert row is not None
        batch = AnnotationBatch.model_validate(row.batch)
    return {record.sample_id: record.boxes or () for record in batch.annotations}


def _export(runner: _Runner, project: Project, version_id: str, split_id: str, fmt: str) -> bytes:
    runner(
        "export_dataset",
        {
            "dataset_id": project.dataset_id,
            "version_id": version_id,
            "split_set_id": split_id,
            "format": fmt,
            "destination": f"production-roundtrip.{fmt}.tar",
        },
    )
    return (data_dir() / "exports" / f"production-roundtrip.{fmt}.tar").read_bytes()


def _members(archive: bytes) -> dict[str, bytes]:
    with tarfile.open(fileobj=io.BytesIO(archive)) as opened:
        result: dict[str, bytes] = {}
        for member in opened:
            stream = opened.extractfile(member) if member.isfile() else None
            if stream is not None:
                result[member.name] = stream.read()
        return result


def _coco_files(members: dict[str, bytes]) -> list[dict[str, object]]:
    return [
        {"filename": PurePosixPath(name).name, "content": content.decode()}
        for name, content in sorted(members.items())
        if PurePosixPath(name).match("annotations/instances_*.json")
    ]


def _yolo_files(members: dict[str, bytes]) -> tuple[list[dict[str, object]], dict[str, str]]:
    manifest = json.loads(members["MANIFEST.json"])
    names = yaml.safe_load(members["data.yaml"])["names"]
    files: list[dict[str, object]] = []
    for item in manifest["files"]:
        image = PurePosixPath(item["path"])
        label = PurePosixPath("labels", *image.parts[1:]).with_suffix(".txt")
        width, height = Image.open(io.BytesIO(members[str(image)])).size
        files.append(
            {
                "filename": label.name,
                "sample_id": item["sample_id"],
                "image_width": width,
                "image_height": height,
                "content": members[str(label)].decode(),
            }
        )
    return files, {str(index): str(name) for index, name in names.items()}


def _imported_boxes(
    db: Database, project: Project, revision_ids: list[str]
) -> dict[str, tuple[AnnotationBox, ...]]:
    result: dict[str, tuple[AnnotationBox, ...]] = {}
    for task in list_tasks(db, project.id):
        for revision in list_revisions(db, task.id):
            if revision.id in revision_ids:
                assert (revision.source, revision.model_name) == ("model", "Round-trip import")
                result[task.sample_id] = revision.annotation.boxes or ()
    return result


def _assert_boxes_match(
    actual: Mapping[str, tuple[AnnotationBox, ...]],
    expected: Mapping[str, tuple[AnnotationBox, ...]],
    tolerance: float,
) -> None:
    assert actual.keys() == expected.keys()
    for sample, boxes in expected.items():
        assert len(actual[sample]) == len(boxes)
        for left, right in zip(actual[sample], boxes, strict=True):
            assert left.category == right.category
            for name in ("x1", "y1", "x2", "y2"):
                assert getattr(left, name) == pytest.approx(getattr(right, name), abs=tolerance)


def test_finalized_version_training_exports_reimport_as_identical_predictions(
    db: Database, tmp_path: Path
) -> None:
    """R1/R7: COCO and YOLO exports of a finalized version import back without box drift."""
    runner = _Runner(db)
    flow = personal_flow(db, tmp_path / "production", runner)
    assert flow.output_version is not None
    expected = _finalized_boxes(db, flow.output_version)
    assert len(expected) == 2
    assert all(expected.values())
    split = create_split(
        db,
        flow.project.dataset_id,
        flow.output_version,
        SplitRequest(name="production-roundtrip", avoid_leakage=False),
    )
    runner(
        "register_model",
        {
            "model": {
                "id": "roundtrip",
                "name": "Round-trip import",
                "version": "export",
                "provider": "import",
            }
        },
    )
    for fmt, tolerance in (("coco", 0.0), ("yolo", _PIXEL_TOLERANCE)):
        members = _members(_export(runner, flow.project, flow.output_version, split.id, fmt))
        assert json.loads(members["MANIFEST.json"])["annotation_count"] == 2
        files, mapping = (_coco_files(members), {}) if fmt == "coco" else _yolo_files(members)
        project = Project.model_validate(
            runner(
                "create_project",
                {
                    "name": f"Round-trip {fmt}",
                    "dataset_id": flow.project.dataset_id,
                    "version_id": flow.output_version,
                    "label_set_id": flow.project.label_set_id,
                },
            ).root
        )
        runner("split_packages", {"project_id": project.id})
        imported = runner(
            "import_predictions",
            {
                "project_id": project.id,
                "model_id": "roundtrip",
                "format": fmt,
                "category_mapping": mapping,
                "files": files,
            },
        )
        assert imported.root["failures"] == []
        revision_ids = imported.root["revision_ids"]
        assert isinstance(revision_ids, list)
        assert len(revision_ids) == 2
        actual = _imported_boxes(db, project, [str(value) for value in revision_ids])
        _assert_boxes_match(actual, expected, tolerance)
