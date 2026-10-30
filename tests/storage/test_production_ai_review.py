# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""AI pre-review on submission: risk evidence, review sampling, exemption audit and personal."""

import random
from pathlib import Path

from sqlalchemy import select

from datakeel.actions.models import ActionContext
from datakeel.actions.production_parameters import SaveRevisionParams
from datakeel.actions.service import prepare_action
from datakeel.core.annotation_models import AnnotationBox, AnnotationRecord
from datakeel.core.data_asset_models import AccessContext
from datakeel.core.production_models import ProductionTask
from datakeel.core.workbench_models import WorkbenchProjectQuery
from datakeel.storage.action_rows import ActionAuditRow
from datakeel.storage.database import Database
from datakeel.storage.production_ai_review import EXEMPT_NOTE
from datakeel.storage.production_queries import get_task
from datakeel.storage.production_revisions import append_revision
from datakeel.storage.production_tasks import require_task
from datakeel.storage.workbench_reads import workbench_project, workbench_task
from tests.prelabel_support import seed_cloud_project
from tests.production_flow_support import action_payload
from tests.workbench_helpers import run_action

CALLER = AccessContext(actor="local", entry="ask", scope="query")
NORMAL = (10.0, 10.0, 40.0, 50.0)


def _record(
    task: ProductionTask, boxes: list[tuple[float, float, float, float]]
) -> AnnotationRecord:
    return AnnotationRecord(
        sample_id=task.sample_id,
        annotator_id="local",
        boxes=tuple(
            AnnotationBox(category="cat", x1=box[0], y1=box[1], x2=box[2], y2=box[3])
            for box in boxes
        ),
        image_width=96,
        image_height=80,
    )


def _draft(db: Database, task: ProductionTask, confidence: float) -> str:
    with db.session() as session:
        revision = append_revision(
            session,
            require_task(session, task.id),
            SaveRevisionParams(
                request_id=f"draft-{task.id}",
                task_id=task.id,
                previous_revision_id=None,
                annotation=_record(task, [NORMAL]),
                source="model",
                model_name="fixture",
                model_version="1",
                confidence=confidence,
                object_confidences=(confidence,),
            ),
            "local",
        )
        session.commit()
    return revision.id


def _submit(
    db: Database,
    task: ProductionTask,
    boxes: list[tuple[float, float, float, float]],
    *,
    group: bool = True,
    previous: str | None = None,
) -> None:
    if group:
        run_action(db, "assign_tasks", {"task_ids": [task.id], "actor": "local"})
    run_action(
        db,
        "save_revision",
        {
            "task_id": task.id,
            "previous_revision_id": previous,
            "annotation": _record(task, boxes).model_dump(mode="json"),
        },
    )
    run_action(db, "submit_task", {"task_id": task.id})


def _audits(db: Database) -> list[str]:
    with db.session() as session:
        rows = session.scalars(select(ActionAuditRow).where(ActionAuditRow.phase == "AI_PREREVIEW"))
        return [str(row.detail["message"]) for row in rows]


def test_full_sampling_keeps_every_group_submission_in_review(db: Database, tmp_path: Path) -> None:
    """At the default 100% ratio every submission waits for a reviewer, as before."""
    project, tasks = seed_cloud_project(db, tmp_path / "images", count=2, tier="group")
    assert project.review_sample_rate == 1
    for task in tasks:
        _submit(db, task, [NORMAL])
    assert {get_task(db, task.id).state for task in tasks} == {"submitted"}
    review = workbench_task(db, tasks[0].id, CALLER).ai_review
    assert review is not None
    assert (review.decision, review.sample_rate, review.high_risk) == ("review", 1, False)
    assert review.revision_id == get_task(db, tasks[0].id).latest_revision_id
    assert not _audits(db)


def test_lowering_the_ratio_needs_signed_approval(db: Database, tmp_path: Path) -> None:
    """Reviewing fewer submissions is a signed decision; raising it back is not."""
    project, _ = seed_cloud_project(db, tmp_path / "images", count=1, tier="group")

    def needs_approval(rate: float) -> bool:
        plan = prepare_action(
            db,
            "configure_project",
            action_payload(
                "configure_project", {"project_id": project.id, "review_sample_rate": rate}
            ),
            ActionContext(actor="local"),
        )
        return plan.requires_approval

    assert needs_approval(0.5)
    assert not needs_approval(1)
    run_action(db, "configure_project", {"project_id": project.id, "review_sample_rate": 0.5})
    assert needs_approval(0.2)
    assert not needs_approval(0.8)


def test_low_risk_is_exempted_with_audit_and_high_risk_still_reviewed(
    db: Database, tmp_path: Path
) -> None:
    """Below the sample ratio low-risk work passes with the audit note; risky work never does."""
    project, tasks = seed_cloud_project(db, tmp_path / "images", count=2, tier="group")
    run_action(db, "configure_project", {"project_id": project.id, "review_sample_rate": 0.0001})
    _submit(db, tasks[0], [NORMAL])
    assert get_task(db, tasks[0].id).state == "approved"
    exempt = workbench_task(db, tasks[0].id, CALLER).ai_review
    assert exempt is not None
    assert exempt.decision == "exempt"
    assert exempt.note.startswith(EXEMPT_NOTE)
    audits = _audits(db)
    assert len(audits) == 1
    assert "AI 预审低风险，按抽检比例免审" in audits[0]  # noqa: RUF001  # Specified wording.
    assert "sample_rate=0.0001" in audits[0]
    assert f"risk={exempt.risk:.4f}" in audits[0]
    draft = _draft(db, tasks[1], 0.9)
    _submit(db, tasks[1], [], previous=draft)
    assert get_task(db, tasks[1].id).state == "submitted"
    risky = workbench_task(db, tasks[1].id, CALLER).ai_review
    assert risky is not None
    assert risky.high_risk
    assert risky.decision == "review"
    assert [reason.code for reason in risky.reasons] == ["prelabel_disagreement"]
    queue = workbench_project(db, project.id, CALLER, WorkbenchProjectQuery(view="review"))
    assert [task.id for task in queue.tasks] == [tasks[1].id]
    assert queue.task_risks[0].risk_reasons[0].code == "prelabel_disagreement"


def test_personal_submission_is_flagged_but_never_blocked(db: Database, tmp_path: Path) -> None:
    """A personal annotator sees the risk for themself; the task still passes."""
    _, tasks = seed_cloud_project(db, tmp_path / "images", count=1)
    draft = _draft(db, tasks[0], 0.95)
    _submit(db, tasks[0], [], group=False, previous=draft)
    assert get_task(db, tasks[0].id).state == "approved"
    review = workbench_task(db, tasks[0].id, CALLER).ai_review
    assert review is not None
    assert (review.decision, review.high_risk) == ("personal", True)
    assert not _audits(db)


def _box(rng: random.Random, planted: str | None) -> list[tuple[float, float, float, float]]:
    x1, y1 = rng.uniform(5, 15), rng.uniform(5, 15)
    width, height = rng.uniform(26, 34), rng.uniform(36, 44)
    if planted == "tiny":
        width, height = width / 6, height / 6
    if planted == "thin":
        width, height = width / 5, height * 1.5
    box = (x1, y1, x1 + width, min(79.0, y1 + height))
    return [box, box] if planted == "duplicate" else [box]


def test_planted_errors_rank_in_the_top_fifth(db: Database, tmp_path: Path) -> None:
    """Size, shape and duplicate mistakes among thirty tasks fill the riskiest 20%."""
    rng = random.Random(31)  # noqa: S311  # Reproducible geometry, not security.
    _, tasks = seed_cloud_project(db, tmp_path / "images", count=30, tier="group")
    plants = {18: "tiny", 21: "thin", 23: "duplicate", 25: "tiny", 27: "thin", 29: "duplicate"}
    for index, task in enumerate(tasks):
        _submit(db, task, _box(rng, plants.get(index)))
    risks = {
        task.id: (workbench_task(db, task.id, CALLER).ai_review, index)
        for index, task in enumerate(tasks)
    }
    ranked = sorted(risks.values(), key=lambda item: -(item[0].risk if item[0] else 0))
    top = {index for _, index in ranked[: len(tasks) // 5]}
    assert len(top & set(plants)) / len(plants) >= 0.8
