# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Every component survives real revisions, personal approval, finalization and native exports."""

import json
import tarfile
from pathlib import Path

import pytest
from sqlalchemy import select

from datakeel.core.annotation_models import AnnotationBatch, AnnotationRecord
from datakeel.core.training_export_models import TrainingAnnotationImport
from datakeel.core.training_models import SplitRequest
from datakeel.storage.annotation_rows import AnnotationBatchRow
from datakeel.storage.database import Database, data_dir
from datakeel.storage.production_queries import list_revisions
from datakeel.storage.training_import import import_training_annotations
from datakeel.storage.training_store import create_split
from datakeel.training.native import import_annotations_jsonl
from tests.workbench_helpers import ComponentKind, annotation_for, run_action, seed_workbench


def _export_content(expected_count: int) -> str:
    with tarfile.open(data_dir() / "exports/workbench-native.tar") as archive:
        stream = archive.extractfile("annotations.jsonl")
        assert stream is not None
        content = stream.read().decode()
        manifest_stream = archive.extractfile("MANIFEST.json")
        assert manifest_stream is not None
        assert json.load(manifest_stream)["annotation_count"] == expected_count
    return content


@pytest.mark.parametrize("kind", ["box", "polygon", "classification", "text_span"])
def test_all_components_roundtrip_finalization_export_and_reimport(
    db: Database, tmp_path: Path, kind: ComponentKind
) -> None:
    """Attributes, nested spans and fractional source coordinates remain exact through P29/P27."""
    project, tasks = seed_workbench(db, tmp_path / "native", kind)
    expected: list[AnnotationRecord] = []
    for task in tasks:
        run_action(
            db,
            "save_revision",
            {
                "task_id": task.id,
                "previous_revision_id": None,
                "annotation": annotation_for(kind, task.sample_id).model_dump(mode="json"),
            },
        )
        expected.append(list_revisions(db, task.id)[0].annotation)
        run_action(db, "submit_task", {"task_id": task.id})
    finalized = run_action(db, "finalize_project", {"project_id": project.id})
    version_id = str(finalized.root["version_id"])
    with db.session() as session:
        final_row = session.scalar(
            select(AnnotationBatchRow).where(AnnotationBatchRow.version_id == version_id)
        )
        assert final_row is not None
        frozen = AnnotationBatch.model_validate(final_row.batch)
        assert sorted(frozen.annotations, key=lambda a: a.sample_id) == sorted(
            expected, key=lambda a: a.sample_id
        )
    split = create_split(
        db, project.dataset_id, version_id, SplitRequest(name="native", avoid_leakage=False)
    )
    run_action(
        db,
        "export_dataset",
        {
            "dataset_id": project.dataset_id,
            "version_id": version_id,
            "split_set_id": split.id,
            "format": "annotations_jsonl",
            "destination": "workbench-native.tar",
        },
    )
    content = _export_content(4 if kind == "text_span" else 2)
    restored = import_annotations_jsonl(content)
    assert sorted(restored, key=lambda a: a.sample_id) == sorted(
        expected, key=lambda a: a.sample_id
    )
    report = import_training_annotations(
        db,
        project.dataset_id,
        version_id,
        TrainingAnnotationImport(
            format="annotations_jsonl", idempotency_key="roundtrip", annotations_jsonl=content
        ),
    )
    with db.session() as session:
        row = session.get(AnnotationBatchRow, report.id)
        assert row is not None
        assert AnnotationBatch.model_validate(row.batch).annotations == restored


def test_mixed_template_components_finalize_and_export_without_losing_properties(
    db: Database, tmp_path: Path
) -> None:
    """A shared box/classification template retains both enabled components through finalization."""
    project, tasks = seed_workbench(db, tmp_path / "mixed")
    run_action(
        db,
        "create_label_set",
        {
            "target": "template",
            "operation": "update",
            "template": {
                "id": "wb-template",
                "name": "Mixed",
                "annotation_type": "box",
                "revision": 1,
                "component_config": {
                    "components": ["box", "classification"],
                    "label_mode": "multi",
                },
            },
        },
    )
    # TAILS-4 R1: a template change reaches an existing project only through a signed upgrade.
    run_action(db, "upgrade_project_template", {"project_id": project.id})
    expected: list[AnnotationRecord] = []
    for task in tasks:
        annotation = annotation_for("box", task.sample_id).model_copy(update={"labels": ("Cat",)})
        run_action(
            db,
            "save_revision",
            {
                "task_id": task.id,
                "previous_revision_id": None,
                "annotation": annotation.model_dump(mode="json"),
            },
        )
        expected.append(list_revisions(db, task.id)[0].annotation)
        run_action(db, "submit_task", {"task_id": task.id})
    finalized = run_action(db, "finalize_project", {"project_id": project.id})
    version_id = str(finalized.root["version_id"])
    split = create_split(
        db, project.dataset_id, version_id, SplitRequest(name="mixed", avoid_leakage=False)
    )
    run_action(
        db,
        "export_dataset",
        {
            "dataset_id": project.dataset_id,
            "version_id": version_id,
            "split_set_id": split.id,
            "format": "annotations_jsonl",
            "destination": "workbench-native.tar",
        },
    )
    restored = import_annotations_jsonl(_export_content(4))
    assert sorted(restored, key=lambda item: item.sample_id) == sorted(
        expected, key=lambda item: item.sample_id
    )
    assert all(record.labels == ("cat",) and record.boxes for record in restored)
