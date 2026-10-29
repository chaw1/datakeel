# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Production history survives upgrades and finalized annotations pass release reconciliation."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select

from datakeel.actions import service
from datakeel.actions.models import ActionContext, ApprovalDecision, ExecuteRequest
from datakeel.core.annotation_models import AnnotationBatch
from datakeel.core.models import BoundaryModel, JsonDocument, LineageEvent
from datakeel.core.production_models import AnnotationRevision, Project
from datakeel.delivery.reconcile import reconcile
from datakeel.storage.action_rows import ActionAuditRow
from datakeel.storage.annotation_rows import AnnotationBatchRow
from datakeel.storage.delivery_service import export_release, reconcile_release
from datakeel.storage.events import all_events
from datakeel.storage.production_queries import list_revisions, list_tasks
from datakeel.storage.release_service import get_release
from tests.production_flow_support import action_payload, personal_flow
from tests.production_helpers import production_fixture

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from datakeel.core.production_models import ProductionTask
    from datakeel.storage.database import Database


class _History(BoundaryModel):
    revisions: dict[str, AnnotationRevision]
    audits: dict[str, JsonDocument]
    lineage: dict[str, LineageEvent]


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
        return JsonDocument.model_validate(run.receipt.quality["details"])


def _history(db: Database, tasks: tuple[ProductionTask, ...]) -> _History:
    revisions = {
        revision.id: revision for task in tasks for revision in list_revisions(db, task.id)
    }
    with db.session() as session:
        audits = {
            row.id: JsonDocument.model_validate(
                {
                    "id": row.id,
                    "plan_id": row.plan_id,
                    "action_type": row.action_type,
                    "phase": row.phase,
                    "status": row.status,
                    "actor": row.actor,
                    "session_id": row.session_id,
                    "detail": row.detail,
                    "created_at": row.created_at,
                }
            )
            for row in session.scalars(select(ActionAuditRow))
        }
        lineage = {event.event_id: event for event in all_events(session)}
    return _History(revisions=revisions, audits=audits, lineage=lineage)


def _assert_history_preserved(before: _History, after: _History) -> None:
    assert before.revisions
    assert before.audits
    assert before.lineage
    assert all(after.revisions.get(key) == value for key, value in before.revisions.items())
    assert all(after.audits.get(key) == value for key, value in before.audits.items())
    assert all(after.lineage.get(key) == value for key, value in before.lineage.items())


def _approve_identical_records(runner: _Runner, tasks: tuple[ProductionTask, ...]) -> None:
    for task in tasks:
        annotation = {"sample_id": task.sample_id, "annotator_id": "local", "labels": ["cat"]}
        first = runner(
            "save_revision",
            {"task_id": task.id, "previous_revision_id": None, "annotation": annotation},
        )
        runner(
            "save_revision",
            {
                "task_id": task.id,
                "previous_revision_id": first.root["id"],
                "annotation": annotation,
            },
        )
        runner("submit_task", {"task_id": task.id})


def _batch(db: Database, version_id: str) -> AnnotationBatch:
    with db.session() as session:
        row = session.scalar(
            select(AnnotationBatchRow).where(AnnotationBatchRow.version_id == version_id)
        )
        assert row is not None
        return AnnotationBatch.model_validate(row.batch)


def test_upgrade_preserves_each_history_record_and_matches_personal_finalized_annotations(
    db: Database,
) -> None:
    """Forward upgrades preserve history and match the personal control annotations."""
    project, tasks = production_fixture(db, count=2)
    runner = _Runner(db)
    control = Project.model_validate(
        runner(
            "create_project",
            {
                "name": "Personal control",
                "dataset_id": project.dataset_id,
                "version_id": project.version_id,
                "label_set_id": project.label_set_id,
            },
        ).root
    )
    runner("split_packages", {"project_id": control.id})
    _approve_identical_records(runner, list_tasks(db, control.id))
    _approve_identical_records(runner, tasks)
    original = _batch(
        db, str(runner("finalize_project", {"project_id": control.id}).root["version_id"])
    )
    before = _history(db, tasks)
    for tier in ("group", "team"):
        runner("upgrade_project", {"project_id": project.id, "workflow_tier": tier})
        _assert_history_preserved(before, _history(db, tasks))
    upgraded = _batch(
        db, str(runner("finalize_project", {"project_id": project.id}).root["version_id"])
    )
    _assert_history_preserved(before, _history(db, tasks))
    original_records = {item.sample_id: item for item in original.annotations}
    assert {item.sample_id: item for item in upgraded.annotations} == original_records
    assert len(before.revisions) == 4


def test_finalized_personal_version_publishes_and_passes_both_release_reconcilers(
    db: Database,
    tmp_path: Path,
) -> None:
    """The existing P16 publisher and independent backend/offline checks accept P29 final output."""
    runner = _Runner(db)
    flow = personal_flow(db, tmp_path / "production", runner)
    assert flow.output_version is not None
    publication = runner(
        "publish_release",
        {
            "dataset_id": flow.project.dataset_id,
            "version_id": flow.output_version,
            "tag": "v1.0.0",
        },
    )
    release_id = str(publication.root["release_id"])
    release = get_release(db, release_id)
    assert release.version_id == flow.output_version
    assert release.file_count == 2
    assert (release.summary.annotation_count, release.summary.label_count) == (2, 2)
    backend = reconcile_release(db, release_id)
    offline = reconcile(export_release(db, release_id, tmp_path / "delivery"))
    for report in (backend, offline):
        assert report.passed
        assert {check.name for check in report.categories} == {
            "file_count",
            "bytes",
            "hashes",
            "annotations",
            "metadata",
            "lineage",
        }
        assert all(check.passed and not check.differences for check in report.categories)
