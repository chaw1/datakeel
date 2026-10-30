# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Seed a registered team-tier production project and verify claim exclusivity afterwards."""

from __future__ import annotations

from collections import defaultdict
from itertools import pairwise
from typing import TYPE_CHECKING, cast

from sqlalchemy import select

from datakeel.actions import service
from datakeel.actions.models import ActionContext, ExecuteRequest
from datakeel.actions.production_parameters import CreateProjectParams, SplitPackagesParams
from datakeel.core.models import FileItem, JsonDocument, new_id, utcnow
from datakeel.core.production_catalog_models import LabelSet, ProductionLabel
from datakeel.core.production_models import Assignment
from datakeel.storage.database import Database, DatasetRow, VersionRow
from datakeel.storage.production_catalog_rows import ProductionLabelSetRow
from datakeel.storage.production_projects import create_project, split_packages
from datakeel.storage.production_rows import ProductionAssignmentRow, ProductionTaskRow

if TYPE_CHECKING:
    from collections.abc import Mapping

    from pydantic import JsonValue

PACKAGE_SIZE = 1000


def run_action(
    db: Database, action: str, values: Mapping[str, object], actor: str
) -> dict[str, JsonValue]:
    """Prepare and execute one reversible controlled action as a person would."""
    plan = service.prepare_action(
        db,
        action,
        JsonDocument.model_validate({"request_id": new_id(), **values}),
        ActionContext(actor=actor),
    )
    run = service.execute_plan(
        db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest, actor=actor)
    )
    if run.status != "SUCCEEDED" or run.receipt is None:
        message = f"{action} did not succeed: {run.error}"
        raise RuntimeError(message)
    details = run.receipt.quality["details"]
    if not isinstance(details, dict):
        message = f"{action} returned no business details"
        raise TypeError(message)
    return cast("dict[str, JsonValue]", details)


def seed_project(db: Database, tasks: int, lease_minutes: int) -> str:
    """Create generated manifests, a published vocabulary and one team project."""
    files = [
        FileItem(id=f"b8-{index:07d}", path=f"b8/{index}.png", filename=f"{index}.png")
        for index in range(tasks)
    ]
    labels = LabelSet(
        id="b8-labels",
        version=1,
        name="B8 labels",
        published=True,
        labels=(ProductionLabel(id="cat", name="Cat"), ProductionLabel(id="dog", name="Dog")),
        created_at=utcnow(),
    )
    with db.session() as session:
        db.lock_writes(session)
        dataset = DatasetRow(name="B8 team", files=[item.model_dump(mode="json") for item in files])
        session.add(dataset)
        session.flush()
        version = VersionRow(dataset_id=dataset.id, manifest=dataset.files)
        session.add(version)
        session.add(
            ProductionLabelSetRow(
                id="b8-labels:1",
                label_set_id=labels.id,
                version=1,
                published=True,
                payload=labels.model_dump(mode="json"),
            )
        )
        session.flush()
        project = create_project(
            session,
            CreateProjectParams(
                request_id=new_id(),
                name="B8 team project",
                dataset_id=dataset.id,
                version_id=version.id,
                label_set_id=labels.id,
                workflow_tier="team",
                lease_minutes=lease_minutes,
            ),
            "local",
        )
        split_packages(
            session,
            SplitPackagesParams(
                request_id=new_id(), project_id=project.id, package_size=PACKAGE_SIZE
            ),
        )
        session.commit()
    return project.id


def register_annotators(db: Database, project_id: str, actors: tuple[str, ...]) -> None:
    """Register an administrator and bind every virtual annotator's project role."""
    run_action(db, "manage_users", {"operation": "create", "user_id": "local"}, "local")
    for actor in actors:
        run_action(db, "manage_users", {"operation": "create", "user_id": actor}, "local")
        run_action(
            db,
            "manage_users",
            {
                "operation": "bind_role",
                "user_id": actor,
                "role_id": "annotator",
                "project_id": project_id,
            },
            "local",
        )


def claim_overlaps(db: Database, project_id: str) -> dict[str, int]:
    """Count annotation assignments whose holding windows overlap on the same task."""
    windows: dict[str, list[Assignment]] = defaultdict(list)
    with db.session() as session:
        rows = session.scalars(
            select(ProductionAssignmentRow.payload)
            .join(ProductionTaskRow, ProductionTaskRow.id == ProductionAssignmentRow.task_id)
            .where(
                ProductionTaskRow.project_id == project_id,
                ProductionAssignmentRow.stage == "annotation",
            )
        )
        for payload in rows:
            assignment = Assignment.model_validate(payload)
            windows[assignment.task_id].append(assignment)
    overlaps = 0
    expired = 0
    for history in windows.values():
        ordered = sorted(history, key=lambda item: (item.created_at, item.id))
        for previous, following in pairwise(ordered):
            expired += previous.end_reason == "expired"
            if previous.active or (
                previous.ended_at is not None and previous.ended_at > following.created_at
            ):
                overlaps += 1
    return {
        "assignment_rows": sum(len(history) for history in windows.values()),
        "claimed_tasks": len(windows),
        "duplicate_claims": overlaps,
        "expired_then_claimed_again": expired,
    }
