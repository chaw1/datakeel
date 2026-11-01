# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""v0.19.0 rules at planning: per-person limit, review separation, template lock, cloud runs."""

from __future__ import annotations

from typing import TYPE_CHECKING

from datakeel.core.intent_models import PageContext
from datakeel.storage.production_catalog_rows import ProductionLabelSetRow
from datakeel.storage.production_queries import get_project, get_task
from tests.intents.planning_support import SOUTH, planned, steps, two_projects
from tests.prelabel_support import cloud_model, seed_cloud_project
from tests.production_team_ops import review, save, submit
from tests.production_team_support import ServiceRunner
from tests.workbench_helpers import run_action

if TYPE_CHECKING:
    from pathlib import Path

    from datakeel.core.intent_models import IntentResult
    from datakeel.storage.database import Database


def _assign(db: Database, text: str, values: dict[str, object]) -> IntentResult:
    return planned(db, text, [steps(("assign_tasks", values))], PageContext())


def test_a_dispatch_over_the_per_person_limit_is_said_before_a_card(db: Database) -> None:
    """Wang holds two open tasks under a limit of two: a third is refused, Li gets it."""
    _, south, tasks = two_projects(db)
    ServiceRunner(db)("configure_project", {"project_id": south.id, "max_active_tasks": 2}, "boss")
    over = _assign(db, "把南区车道第 5 条派给小王", {"task_ids": tasks[4:5], "actor": "wang"})
    assert over.kind != "plan", over.text
    assert all(word in over.text for word in ("小王", "2 条在做", "最多 2 条")), over.text
    fits = _assign(db, "把南区车道第 5 条派给小李", {"task_ids": tasks[4:5], "actor": "li"})
    assert fits.kind == "plan", fits.text


def test_a_dispatch_never_raises_the_project_limit(db: Database) -> None:
    """One dispatch may lower the project's limit only, as preparation refuses a higher one."""
    _, south, tasks = two_projects(db)
    ServiceRunner(db)("configure_project", {"project_id": south.id, "max_active_tasks": 3}, "boss")
    values = {"task_ids": tasks[4:5], "actor": "li", "max_active_tasks": 5}
    raised = _assign(db, "南区车道第 5 条派给小李, 这次上限放到 5", values)
    assert raised.kind != "plan", raised.text
    assert "只能调低" in raised.text, raised.text


def test_review_never_goes_back_to_an_annotator_after_a_rework_handover(db: Database) -> None:
    """Li annotated #3, it came back for rework and was handed to Wang: neither may review it."""
    _, _, tasks = two_projects(db)
    run, rework = ServiceRunner(db), tasks[2]
    review(db, rework, "zhao", approve=False)
    run("revoke_assignment", {"task_id": rework, "reason": "转给小王返工"}, "boss")
    run("assign_tasks", {"task_ids": [rework], "actor": "wang"}, "boss")
    save(db, rework, "wang")
    submit(db, rework, "wang")
    assert get_task(db, rework).annotator_id == "wang"
    for person, name in (("li", "小李"), ("wang", "小王")):
        values = {"task_ids": [rework], "actor": person, "stage": "review"}
        refused = _assign(db, f"南区车道第 3 条派给{name}审", values)
        assert refused.kind != "plan", refused.text
        assert all(word in refused.text for word in (name, "标过", "换一个审核人")), refused.text
    values = {"task_ids": [rework], "actor": "zhao", "stage": "review"}
    allowed = _assign(db, "南区车道第 3 条派给小赵审", values)
    assert allowed.kind == "plan", allowed.text


def test_a_template_upgrade_needs_a_newer_version_to_move_to(db: Database) -> None:
    """A project already on the newest versions is told so; a newer published one is planned."""
    _, south, _ = two_projects(db)
    upgrade = steps(("upgrade_project_template", {"project_id": SOUTH}))
    same = planned(db, "把南区车道升级到最新的模板和标签集", [upgrade], PageContext())
    assert same.kind != "plan", same.text
    assert "没有可升级的" in same.text, same.text
    project = get_project(db, south.id)
    with db.session() as session:
        db.lock_writes(session)
        row = session.get(ProductionLabelSetRow, f"{project.label_set_id}:1")
        assert row is not None
        session.add(
            ProductionLabelSetRow(
                id=f"{project.label_set_id}:2",
                label_set_id=project.label_set_id,
                version=2,
                published=True,
                payload={**row.payload, "version": 2, "id": project.label_set_id},
            )
        )
        session.commit()
    newer = planned(db, "把南区车道升级到最新的模板和标签集", [upgrade], PageContext())
    assert newer.kind == "plan", newer.text


def test_a_cloud_pre_label_card_says_it_sends_images_out_and_what_it_costs(
    db: Database, tmp_path: Path
) -> None:
    """The card marks a cloud run external, prices it like preparation and signs above budget."""
    project, _ = seed_cloud_project(db, tmp_path / "images", count=4, tier="team")
    run_action(db, "register_model", {"model": cloud_model()})
    context = PageContext(project_id=project.id)
    text = "用 fixture-vl 模型给这个项目跑一遍预标注"
    for budget, signed in ((0.0, True), (100.0, False)):
        values = {"project_id": project.id, "model_id": "vision", "budget": budget}
        result = planned(db, text, [steps(("run_prelabel", values))], context, actor="local")
        assert result.kind == "plan", result.text
        assert result.chain is not None
        step = result.chain.steps[0]
        assert step.estimate.external, step.estimate
        assert step.estimate.requires_approval is signed, step.estimate
        spend = next(detail.value for detail in step.details if detail.label == "预计花费")
        assert "4 张图" in spend, spend
        assert "CNY" in spend, spend
        assert ("要签批" in spend) is signed, spend
