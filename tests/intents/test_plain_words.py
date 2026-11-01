# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Values the state answers are never asked; no internal name reaches a person."""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from datakeel.actions.registry import POLICIES
from datakeel.core.intent_models import ChainStep, PageContext
from datakeel.intents.answers import answer_text, run_read
from datakeel.intents.catalog import build_catalog
from datakeel.intents.describe import describe_step
from datakeel.intents.public_text import allowed_words, leaks, public
from datakeel.intents.wording import field_label, invalid_question, missing_question, refusal
from datakeel.ontology.tool_models import ToolCallContext
from datakeel.storage.production_catalog_rows import ProductionLabelSetRow
from datakeel.storage.production_queries import get_task
from tests.intents.planning_support import SOUTH, planned, shown, steps, two_projects

if TYPE_CHECKING:
    import pytest
    from pydantic import JsonValue

    from datakeel.core.intent_models import IntentResult
    from datakeel.storage.database import Database

SNAKE = re.compile(r"\b[a-z]+_[a-z_]+\b")


def _revisions(result: IntentResult) -> list[object]:
    assert result.kind == "plan", result.text
    assert result.chain is not None
    step = result.chain.steps[-1]
    if step.items:
        return [item.get("revision_id") for item in step.items]
    return [step.params.get("revision_id")]


def test_a_review_uses_the_latest_revision_in_every_entry(db: Database) -> None:
    """Approve, send back with a reason, a group, a chain step, zh and en: never asked."""
    _, south, tasks = two_projects(db)
    latest = [get_task(db, task).latest_revision_id for task in tasks[2:4]]
    page = PageContext(project_id=south.id, task_id=tasks[2])
    approve = steps(("review_task", {"task_id": tasks[2], "decision": "approve"}))
    assert _revisions(planned(db, "这条通过", [approve], page, actor="zhao")) == latest[:1]
    worded = steps(
        ("review_task", {"task_id": tasks[2], "decision": "rework", "revision_id": "最新版"}),
    )
    result = planned(db, "这条退回去, 框画歪了", [worded], page, actor="zhao")
    assert _revisions(result) == latest[:1]
    group = {"$tasks": {"numbers": [3, 4]}}
    both = steps(("review_task", {"task_id": group, "decision": "approve"}))
    result = planned(db, "Approve tasks #3 and #4", [both], page, actor="zhao")
    assert _revisions(result) == latest
    chain = steps(
        ("review_task", {"task_id": tasks[2], "decision": "approve"}),
        ("review_task", {"task_id": tasks[3], "decision": "rework", "issues": ["漏框"]}),
    )
    result = planned(db, "第 3 条通过, 第 4 条退回: 漏框", [chain], page, actor="zhao")
    assert result.chain is not None
    assert [step.params.get("revision_id") for step in result.chain.steps] == latest[:1]
    assert "上一步完成后再规划" in result.text
    second = steps(("review_task", {"task_id": tasks[3], "decision": "rework", "issues": ["漏框"]}))
    later = planned(db, "第 4 条退回: 漏框", [second], page, actor="zhao")
    assert _revisions(later) == latest[1:]


def test_a_review_with_nothing_saved_says_why_instead_of_asking(db: Database) -> None:
    """A task nobody annotated has nothing to review: the reply says so, no revision question."""
    _, south, tasks = two_projects(db)
    empty = steps(("review_task", {"task_id": tasks[4], "decision": "approve"}))
    result = planned(db, "第 5 条通过", [empty], PageContext(project_id=south.id), actor="zhao")
    assert result.kind == "clarify"
    assert result.clarification is not None
    assert result.clarification.fields == []
    assert "还没有保存过标注" in result.text
    english = planned(db, "Approve task 5", [empty], PageContext(project_id=south.id), actor="zhao")
    assert "no saved annotation" in english.text
    assert "revision" not in english.text.casefold()


def test_newest_versions_are_read_not_asked(db: Database) -> None:
    """Publishing means the newest version; a project uses the newest published one."""
    _, south, _ = two_projects(db)
    with db.session() as session:
        db.lock_writes(session)
        first = session.get(ProductionLabelSetRow, f"{south.label_set_id}:1")
        assert first is not None
        payload = {**first.payload, "version": 2, "published": False}
        session.add(
            ProductionLabelSetRow(
                id=f"{south.label_set_id}:2",
                label_set_id=south.label_set_id,
                version=2,
                published=False,
                payload=payload,
            )
        )
        session.commit()
    page = PageContext(label_set_id=south.label_set_id)
    publish = steps(("publish_label_set", {"label_set_id": south.label_set_id}))
    result = planned(db, "把这个标签集发布了", [publish], page)
    assert result.chain is not None, result.text
    assert result.chain.steps[0].params.get("version") == 2
    latest = steps(("publish_label_set", {"label_set_id": south.label_set_id, "version": "latest"}))
    result = planned(db, "Publish the latest version of this label set", [latest], page)
    assert result.chain is not None, result.text
    assert result.chain.steps[0].params.get("version") == 2


def test_choices_refusals_and_failed_reads_speak_plainly(
    db: Database, caplog: pytest.LogCaptureFixture
) -> None:
    """Choices in words, refusals without the action id, failed reads without raw errors."""
    _, south, tasks = two_projects(db)
    page = PageContext(project_id=south.id, task_id=tasks[2])
    undecided = steps(("review_task", {"task_id": tasks[2]}))
    result = planned(db, "审一下这条", [undecided], page, actor="zhao")
    assert result.clarification is not None
    assert {item.label for item in result.clarification.candidates} == {"通过", "打回"}
    assert "decision" not in result.text
    refused = planned(db, "这条通过", [steps(("review_task", {"task_id": tasks[2]}))], page, "wang")
    assert refused.kind == "refuse"
    assert "review_task" not in refused.text
    assert "review_task" not in refusal("review_task", ["production:review"], "en")
    assert "通过、打回" in invalid_question("decision:'approve' or 'rework'", "zh")
    asked = missing_question("assign_tasks", ["actor", "actor"], "zh")
    assert asked.count(field_label("actor", "zh")) == 1
    with caplog.at_level(logging.WARNING):
        context = ToolCallContext(actor="boss")
        answer, text = run_read(db, "project_progress", {"project_id": "nope"}, context, "zh")
    assert answer is None
    assert "nope" not in text
    assert "没能完成" in text
    assert any("project_progress" in record.getMessage() for record in caplog.records)
    data: JsonValue = {"counts": [{"state": "in_review", "count": 2}], "review_count": 3}
    assert "in_review" not in answer_text("project_progress", data, "en")
    assert "review_count" not in answer_text("project_progress", data, "zh")


def test_cards_show_choices_in_words_and_never_internal_names(db: Database) -> None:
    """Every card line, default and reference reads as words in Chinese."""
    _, south, tasks = two_projects(db)
    page = PageContext(project_id=south.id)
    chain = steps(
        ("split_packages", {"project_id": south.id, "group_by": "directory"}),
        ("assign_tasks", {"task_ids": tasks[4:6], "actor": "wang", "strategy": "assign"}),
    )
    result = planned(db, "按目录重新切包, 再把第 5、6 条派给小王", [chain], page)
    assert result.kind == "answer", result.text
    # The already-split first step is answered; the dependent dispatch is deferred.
    assert "已经切过包" in result.text
    assert "上一步完成后再规划" in result.text
    assigned = planned(
        db,
        "把第 5、6 条派给小王",
        [steps(("assign_tasks", {"task_ids": tasks[4:6], "actor": "wang", "strategy": "assign"}))],
        page,
    )
    catalog = build_catalog(db, south.id)
    split = ChainStep(id="s1", action="split_packages", params=chain["steps"][0]["params"])
    split_lines = [detail.value for detail in describe_step(db, split, catalog, "zh")]
    lines = [*split_lines, *shown(assigned).values(), *shown(assigned)]
    assert "按目录" in lines
    assert "指定人" in lines
    assert any("标注 (默认)" in line for line in lines)
    allowed = allowed_words(catalog, result.request)
    for line in lines:
        assert not leaks(line, "zh", allowed), line
        assert not SNAKE.search(line), line


def test_the_outgoing_check_repairs_known_names_and_replaces_the_rest(
    db: Database, caplog: pytest.LogCaptureFixture
) -> None:
    """Known internals become words; unknown internals become a generic sentence and a log."""
    _, south, _ = two_projects(db)
    catalog = build_catalog(db, south.id)
    allowed = allowed_words(catalog, f"{SOUTH} 进度")
    assert not leaks(f"{SOUTH} 的进度", "zh", allowed)
    assert leaks("用 $ref 引用 s1", "zh", allowed)
    assert leaks("项目 6d924f29-ecc2-420f-9573-f1ef0124f472 的进度", "zh", allowed)
    assert leaks("按 skill 派给小王", "zh", allowed) == ["skill"]
    assert not leaks("assign by skill", "en", allowed)
    assert not leaks("frame_001.png 和 red_light.jpg", "zh", allowed)
    repaired = public("要 assign_tasks, 还缺 package_size", "zh", catalog, allowed)
    assert "assign_tasks" not in repaired
    assert "package_size" not in repaired
    assert "每包数量" in repaired
    with caplog.at_level(logging.WARNING):
        replaced = public("内部字段 weird_internal_key 出错", "zh", catalog, allowed)
    assert "weird_internal_key" not in replaced
    assert any("weird_internal_key" in record.getMessage() for record in caplog.records)


def test_refusals_and_object_lists_name_things_in_words(db: Database) -> None:
    """Scopes and object kinds read as words; a project named in a read's words narrows it."""
    zh = refusal("assign_tasks", ["production:assign"], "zh")
    assert "「派单」" in zh
    assert "assign" not in zh
    assert "assigning tasks (production:assign)" in refusal(
        "assign_tasks", ["production:assign"], "en"
    )
    reference = {"asset_type": "production_task", "asset_id": "t-1", "namespace": "default"}
    listed: JsonValue = [
        {"asset_ref": reference, "revision": "f" * 64, "properties": {"state": "in_progress"}},
        {"asset_ref": reference, "revision": "e" * 64, "properties": {"annotator_id": "wang"}},
    ]
    sentence = answer_text("production_objects", listed, "zh")
    assert sentence.startswith("找到 2 个任务")
    assert "进行中 1" in sentence
    assert "production_task" not in sentence
    _, south, _ = two_projects(db)
    read = steps(("production_objects", {"kind": "tasks", "project": SOUTH}), kind="answer")
    result = planned(db, f"{SOUTH}里有哪些任务", [read], PageContext())
    assert result.kind == "answer", result.text
    assert result.answer is not None
    assert result.answer.arguments.get("project_id") == south.id
    assert result.answer.arguments.get("kind") == "production_task"
    assert "不能按" not in result.text
    assert "找到 6 个任务" in result.text


def test_cards_show_revisions_tasks_and_budgets_in_words(db: Database) -> None:
    """A review card names the task by its place and the revision as the latest one."""
    _, south, tasks = two_projects(db)
    page = PageContext(project_id=south.id, task_id=tasks[2])
    approve = steps(("review_task", {"task_id": tasks[2], "decision": "approve"}))
    lines = shown(planned(db, "这条通过", [approve], page, actor="zhao"))
    assert lines.get(field_label("task_id", "zh")) == "1 个任务: #3"
    assert "最新保存的那一版" in lines.values()
    catalog = build_catalog(db, south.id)
    sheet = ChainStep(
        id="s1",
        action="generate_datasheet",
        params={"version_id": south.version_id},
        scope=POLICIES["generate_datasheet"][0],
    )
    budget = " ".join(detail.value for detail in describe_step(db, sheet, catalog, "zh"))
    assert "conversation_tokens" not in budget
    assert "每次对话 token 上限 100000" in budget
