# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""AI pre-review catches the four planted error kinds in a one-annotator team project."""

import re
from pathlib import Path

import pytest

from datakeel.annotation_qa import HIGH_RISK
from datakeel.core.data_asset_models import AccessContext
from datakeel.core.prelabel_models import AIReview
from datakeel.core.production_models import ProductionTask
from datakeel.core.workbench_models import WorkbenchProjectQuery
from datakeel.storage.database import Database
from datakeel.storage.workbench_reads import workbench_project, workbench_task
from tests.ai_review_support import (
    Truth,
    add_draft,
    nudged,
    record,
    seed_team_project,
    submit,
    truth,
)

CALLER = AccessContext(actor="local", entry="ask", scope="query")
REVIEWER = AccessContext(actor="reviewer", entry="ask", scope="query")
SWAPS = (3, 17, 29)
SIZES = {8: "tiny", 22: "huge", 35: "tiny"}
COPIES = {41: 40, 45: 44}
NEAR_WRONG = {41: "missing", 44: "moved"}
MULTI = (12, 33)
_INTERNAL = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}|\('|\['|MAD|z=|\bNone\b")


def _truth(index: int) -> Truth:
    return truth(COPIES.get(index, index))


def _planted(
    index: int, item: Truth
) -> tuple[tuple[str, ...], list[tuple[str, tuple[float, ...]]]]:
    labels, animal, box = (item.scene,), item.animal, nudged(item.box, index)
    if index in SWAPS:
        animal = "dog" if animal == "cat" else "cat"
    if SIZES.get(index) == "tiny":
        box = (box[0], box[1], box[0] + (box[2] - box[0]) / 5, box[1] + (box[3] - box[1]) / 5)
    if SIZES.get(index) == "huge":
        box = (2, 2, 158, 118)
    if NEAR_WRONG.get(index) == "moved":
        box = (box[0] + 45, box[1] + 25, box[2] + 45, box[3] + 25)
    if index in MULTI:
        labels = ("day", "night")
    boxes = [] if NEAR_WRONG.get(index) == "missing" else [(animal, box)]
    return labels, boxes


def _run(
    db: Database, tasks: list[ProductionTask], order: list[int], *, labelled: bool = True
) -> None:
    drafts = {
        index: add_draft(db, task, _truth(index), 0.9 + (index % 5) * 0.01, labelled=labelled)
        for index, task in enumerate(tasks)
    }
    for index in order:
        labels, boxes = _planted(index, _truth(index))
        submit(db, tasks[index], record(tasks[index], labels, boxes), drafts[index])


def _review(db: Database, task: ProductionTask) -> AIReview:
    review = workbench_task(db, task.id, CALLER).ai_review
    assert review is not None
    return review


@pytest.mark.parametrize("draft", ["full", "box-only"])
def test_planted_errors_of_all_four_kinds_fill_the_top_ten(
    db: Database, tmp_path: Path, draft: str
) -> None:
    """Ten planted mistakes in fifty drafted tasks: >= 8 in the top ten, <= 3 false alarms.

    The box-only variant is a model without classification on a labels-and-boxes template.
    """
    project, tasks = seed_team_project(db, tmp_path / "images", 50, COPIES)
    _run(db, tasks, list(range(50)), labelled=draft == "full")
    planted = {*SWAPS, *SIZES, *NEAR_WRONG, *MULTI}
    assert len(planted) == 10
    queue = workbench_project(db, project.id, REVIEWER, WorkbenchProjectQuery(view="review"))
    index = {task.id: position for position, task in enumerate(tasks)}
    ranked = [index[task.id] for task in queue.tasks]
    assert len(ranked) == 50
    reviews = {position: _review(db, task) for position, task in enumerate(tasks)}
    hits = len(set(ranked[:10]) & planted)
    false_alarms = sorted(i for i, item in reviews.items() if item.high_risk and i not in planted)
    print(f"top-10 hits={hits}/10 false high-risk={len(false_alarms)}/40 {false_alarms}")  # noqa: T201  # Report the measured numbers.
    assert hits >= 8
    assert len(false_alarms) <= 3
    # The correct half of each near-duplicate pair matches its draft on the kinds both have.
    correct_halves = sorted({*COPIES, *COPIES.values()} - set(NEAR_WRONG))
    assert [i for i in correct_halves if reviews[i].high_risk] == []
    shown = {risk.task_id: risk for risk in queue.task_risks}
    assert [shown[task.id].ai_risk for task in queue.tasks] == sorted(
        (reviews[index[task.id]].risk for task in queue.tasks), reverse=True
    )
    codes = {i: {reason.code for reason in item.reasons} for i, item in reviews.items()}
    assert all("label_swap" in codes[i] for i in SWAPS)
    assert all("bbox_size_outlier" in codes[i] for i in SIZES)
    assert all("near_duplicate_conflict" in codes[i] for i in (*NEAR_WRONG, *COPIES.values()))
    assert all("multilabel_conflict" in codes[i] for i in MULTI)
    for item in reviews.values():
        for reason in item.reasons:
            text = " ".join((reason.message, reason.message_zh, *reason.evidence))
            assert reason.message_zh, reason.code
            assert not _INTERNAL.search(text), text


def test_size_outlier_submitted_first_is_judged_against_draft_boxes(
    db: Database, tmp_path: Path
) -> None:
    """The first submission already sees every draft box, so a tiny box is an outlier."""
    _, tasks = seed_team_project(db, tmp_path / "images", 24)
    drafts = [add_draft(db, task, truth(index), 0.95) for index, task in enumerate(tasks)]
    item = truth(0)
    tiny = (item.box[0], item.box[1], item.box[0] + 10, item.box[1] + 9)
    submit(db, tasks[0], record(tasks[0], (item.scene,), [(item.animal, tiny)]), drafts[0])
    review = _review(db, tasks[0])
    found = [reason for reason in review.reasons if reason.code == "bbox_size_outlier"]
    assert len(found) == 1
    outlier = found[0]
    assert [(ref.kind, ref.index) for ref in outlier.objects] == [("box", 0)]
    assert (
        outlier.message == 'Box 1 is far larger or smaller than other "Cat" boxes in this project'
    )
    assert review.high_risk


def test_moving_draft_boxes_a_few_pixels_adds_no_risk(db: Database, tmp_path: Path) -> None:
    """Careful work over 95% drafts is low risk even though no box matches to the pixel."""
    _, tasks = seed_team_project(db, tmp_path / "images", 6)
    for index, task in enumerate(tasks):
        draft = add_draft(db, task, truth(index), 0.95)
        item = truth(index)
        boxes = [(item.animal, nudged(item.box, index + 1))]
        submit(db, task, record(task, (item.scene,), boxes), draft)
    assert {(_review(db, task).risk, _review(db, task).reasons) for task in tasks} == {(0, ())}


@pytest.mark.parametrize("wrong_first", [True, False])
def test_near_duplicate_conflict_flags_both_images_whatever_the_order(
    db: Database, tmp_path: Path, *, wrong_first: bool
) -> None:
    """Both halves carry the conflict in the queue; the one that departs from its draft leads."""
    project, tasks = seed_team_project(db, tmp_path / "images", 4, {1: 0})
    drafts = [add_draft(db, task, truth(0 if i == 1 else i), 0.95) for i, task in enumerate(tasks)]
    item = truth(0)
    right = record(tasks[0], (item.scene,), [(item.animal, item.box)])
    wrong = record(tasks[1], (item.scene,), [])
    steps = [(tasks[1], wrong, drafts[1]), (tasks[0], right, drafts[0])]
    for task, annotation, draft in steps if wrong_first else steps[::-1]:
        submit(db, task, annotation, draft)
    queue = workbench_project(db, project.id, REVIEWER, WorkbenchProjectQuery(view="review"))
    shown = {risk.task_id: risk for risk in queue.task_risks}
    for task in tasks[:2]:
        assert "near_duplicate_conflict" in {reason.code for reason in shown[task.id].risk_reasons}
        assert _review(db, task).reasons == shown[task.id].risk_reasons
    assert [task.id for task in queue.tasks] == [tasks[1].id, tasks[0].id]
    assert shown[tasks[1].id].high_risk
    assert not shown[tasks[0].id].high_risk
    assert '"img-01.png"' in next(
        reason.message
        for reason in shown[tasks[0].id].risk_reasons
        if reason.code.startswith("near")
    )


def test_template_exclusive_labels_make_a_multiselect_conflict(
    db: Database, tmp_path: Path
) -> None:
    """The template's exclusive label groups apply to a single annotator's label set."""
    _, tasks = seed_team_project(db, tmp_path / "images", 3)
    item = truth(1)
    draft = add_draft(db, tasks[1], Truth(item.animal, "day", item.box), 0.6)
    both = record(tasks[1], ("day", "night"), [(item.animal, item.box)])
    submit(db, tasks[1], both, draft)
    reasons = {reason.code: reason for reason in _review(db, tasks[1]).reasons}
    assert "multilabel_conflict" in reasons
    conflict = reasons["multilabel_conflict"]
    assert conflict.weight >= HIGH_RISK
    assert conflict.message == (
        'The labels "Day", "Night" should not be used together under this project\'s template'
    )
    assert conflict.message_zh == "按项目模板的设置，「Day」、「Night」不应同时出现"  # noqa: RUF001  # Specified wording.
    assert [(ref.kind, ref.index) for ref in conflict.objects] == [("label_set", 0)]
