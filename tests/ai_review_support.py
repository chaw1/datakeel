# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""A team project of distinct generated images, model drafts and one human submission each.

Every image is a random grid of grey blocks, so perceptual hashes of different images are far
apart; a near-duplicate is the same grid brightened slightly. The template enables boxes and
classification with ``day``/``night`` declared mutually exclusive, so all four review rule
families can fire in one project.
"""

import random
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from datakeel.actions.production_parameters import SaveRevisionParams
from datakeel.core.annotation_models import AnnotationBox, AnnotationRecord
from datakeel.core.production_models import ProductionTask, Project
from datakeel.storage.database import Database, VersionRow
from datakeel.storage.dataset_service import import_paths, list_versions
from datakeel.storage.production_queries import list_tasks
from datakeel.storage.production_revisions import append_revision
from datakeel.storage.production_tasks import require_task
from tests.workbench_helpers import run_action

WIDTH, HEIGHT = 160, 120
_BLOCK = 10


@dataclass(frozen=True)
class Truth:
    """What a careful annotator would submit for one image."""

    animal: str
    scene: str
    box: tuple[float, float, float, float]


def _grid(seed: int) -> Image.Image:
    rng = random.Random(seed)  # noqa: S311  # Reproducible test pixels, not security.
    image = Image.new("RGB", (WIDTH, HEIGHT))
    for top in range(0, HEIGHT, _BLOCK):
        for left in range(0, WIDTH, _BLOCK):
            grey = rng.randrange(256)
            image.paste((grey, grey, grey), (left, top, left + _BLOCK, top + _BLOCK))
    return image


def write_images(directory: Path, count: int, copies: dict[int, int]) -> list[Path]:
    """Write ``count`` distinct images; ``copies`` maps an index to the image it nearly repeats."""
    directory.mkdir(parents=True)
    paths: list[Path] = []
    for index in range(count):
        path = directory / f"img-{index:02d}.png"
        source = copies.get(index)
        image = _grid(source if source is not None else index)
        if source is not None:
            image = image.point([min(255, value + 4) for value in range(256)] * 3)
        image.save(path)
        paths.append(path)
    return paths


def seed_team_project(
    db: Database, directory: Path, count: int, copies: dict[int, int] | None = None
) -> tuple[Project, list[ProductionTask]]:
    """Create the project and return its tasks ordered by image index."""
    paths = write_images(directory, count, copies or {})
    dataset = import_paths(db, "Generated review", paths)
    version = list_versions(db, dataset.id)[0]
    labels = [{"id": name, "name": name.title()} for name in ("cat", "dog", "day", "night")]
    run_action(db, "create_label_set", {"label_set_id": "rv-labels", "labels": labels})
    run_action(db, "publish_label_set", {"label_set_id": "rv-labels", "version": 1})
    config = {
        "components": ["box", "classification"],
        "label_mode": "multi",
        "exclusive_label_groups": [["day", "night"]],
    }
    template = {"id": "rv-template", "name": "Review", "annotation_type": "box"}
    run_action(
        db,
        "create_label_set",
        {"target": "template", "template": {**template, "component_config": config}},
    )
    project = Project.model_validate(
        run_action(
            db,
            "create_project",
            {
                "name": "Review",
                "dataset_id": dataset.id,
                "version_id": version.id,
                "label_set_id": "rv-labels",
                "template_id": "rv-template",
                "workflow_tier": "team",
            },
        ).root
    )
    run_action(db, "split_packages", {"project_id": project.id, "package_size": 1000})
    with db.session() as session:
        row = session.get(VersionRow, project.version_id)
        assert row is not None
        order = {str(item["id"]): str(item["filename"]) for item in row.manifest}
    tasks = sorted(list_tasks(db, project.id), key=lambda task: order[task.sample_id])
    return project, tasks


def record(
    task: ProductionTask, labels: tuple[str, ...], boxes: list[tuple[str, tuple[float, ...]]]
) -> AnnotationRecord:
    """Build a full-size annotation with labels and categorised boxes."""
    return AnnotationRecord(
        sample_id=task.sample_id,
        annotator_id="local",
        labels=labels,
        boxes=tuple(
            AnnotationBox(category=category, x1=box[0], y1=box[1], x2=box[2], y2=box[3])
            for category, box in boxes
        ),
        image_width=WIDTH,
        image_height=HEIGHT,
    )


def add_draft(db: Database, task: ProductionTask, truth: Truth, confidence: float) -> str:
    """Append the model draft (label set then box confidence) and return its id."""
    annotation = record(task, (truth.scene,), [(truth.animal, truth.box)])
    with db.session() as session:
        revision = append_revision(
            session,
            require_task(session, task.id),
            SaveRevisionParams(
                request_id=f"draft-{task.id}",
                task_id=task.id,
                previous_revision_id=None,
                annotation=annotation,
                source="model",
                model_name="fixture",
                model_version="1",
                confidence=confidence,
                object_confidences=(confidence, min(1.0, confidence + 0.02)),
            ),
            "local",
        )
        session.commit()
    return revision.id


def submit(db: Database, task: ProductionTask, annotation: AnnotationRecord, draft: str) -> None:
    """Claim the task, save the annotator's own revision over the draft and submit it."""
    run_action(db, "assign_tasks", {"task_ids": [task.id], "actor": "local"})
    run_action(
        db,
        "save_revision",
        {
            "task_id": task.id,
            "previous_revision_id": draft,
            "annotation": annotation.model_dump(mode="json"),
        },
    )
    run_action(db, "submit_task", {"task_id": task.id})


def truth(index: int) -> Truth:
    """Give each image a plausible, varied correct annotation."""
    x1, y1 = 20 + (index % 5) * 6, 15 + (index % 4) * 5
    width, height = 50 + (index % 7) * 3, 45 + (index % 6) * 3
    return Truth(
        "cat" if index % 2 == 0 else "dog",
        "day" if index % 3 else "night",
        (x1, y1, x1 + width, y1 + height),
    )


def nudged(box: tuple[float, ...], index: int) -> tuple[float, ...]:
    """Move a box by up to three pixels, as careful annotators do."""
    shift = (index % 3) - 1
    return (box[0] + shift, box[1] + 2, box[2] + shift + 1, box[3] + 3)
