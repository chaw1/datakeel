# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""A model may not fill a project nobody named; reads may still use the only project."""

from __future__ import annotations

from typing import TYPE_CHECKING

from datakeel.core.intent_models import PageContext
from datakeel.intents.catalog import CatalogEntry
from datakeel.intents.grounding import mentioned
from datakeel.intents.recipes import match_recipe
from tests.intents.support import model_plan, team

if TYPE_CHECKING:
    from datakeel.storage.database import Database


def _split(project_id: str) -> dict[str, object]:
    step = {"id": "s1", "action": "split_packages", "params": {"project_id": project_id}}
    return {"kind": "plan", "steps": [step]}


def test_unnamed_single_project_copied_by_the_model_is_asked(db: Database) -> None:
    """The sentence and the page name no project, so the write asks which project."""
    project, _ = team(db)
    result = model_plan(db, "把项目切成每包 20 张的任务包", _split(project.id), PageContext())
    assert result.kind == "clarify"
    assert result.clarification is not None
    assert result.clarification.fields == ["project_id"]
    assert [item.id for item in result.clarification.candidates] == [project.id]
    assert result.chain is None


def test_project_from_the_page_or_the_words_is_accepted(db: Database) -> None:
    """The same plan is accepted when the page shows that project or the sentence names it."""
    project, _ = team(db)
    on_page = model_plan(
        db, "每包 20 张切包", _split(project.id), PageContext(project_id=project.id)
    )
    assert on_page.kind == "plan"
    named = model_plan(db, f"把 {project.name} 切成每包 20 张", _split(project.id), PageContext())
    assert named.kind == "plan"
    assert named.chain is not None
    assert named.chain.steps[0].params["project_id"] == project.id


def test_a_read_may_use_the_only_project_without_asking(db: Database) -> None:
    """Answering a question about the only project changes nothing, so it answers."""
    project, _ = team(db)
    payload: dict[str, object] = {
        "kind": "answer",
        "steps": [{"id": "s1", "action": "project_progress", "params": {"project_id": project.id}}],
    }
    result = model_plan(db, "现在做到哪一步了", payload, PageContext())
    assert result.kind == "answer"
    assert result.answer is not None
    assert result.answer.function == "project_progress"


def test_distinctive_parts_of_a_name_count_as_a_mention() -> None:
    """Generic words such as project do not ground; a distinctive part of the name does."""
    entry = CatalogEntry(id="p-1", kind="project", label="Harbor traffic 交通标注")
    assert mentioned(entry, "split the harbor job")
    assert mentioned(entry, "把交通那个切一下")
    assert not mentioned(entry, "split the project")
    assert not mentioned(entry, "把项目切一下")


def test_a_write_missing_its_project_asks_even_with_one_project(db: Database) -> None:
    """Left out by the model and absent from the page: ask, do not take the only project."""
    team(db)
    step: dict[str, object] = {"id": "s1", "action": "split_packages", "params": {}}
    payload: dict[str, object] = {"kind": "plan", "steps": [step]}
    result = model_plan(db, "切成每包 20 张", payload, PageContext())
    assert result.kind == "clarify"
    assert result.clarification is not None
    assert result.clarification.fields == ["project_id"]


def test_project_created_with_its_label_set_is_named_after_it(db: Database) -> None:
    """A model that leaves out the project name gets the new label set's name, not a question."""
    project, _ = team(db)
    label: dict[str, object] = {"name": "街景框", "labels": [{"id": "person", "name": "行人"}]}
    created: dict[str, object] = {
        "label_set_id": {"$ref": "s1.label_set_id"},
        "label_set_version": {"$ref": "s1.label_set_version"},
    }
    payload: dict[str, object] = {
        "kind": "plan",
        "steps": [
            {"id": "s1", "action": "create_label_set", "params": label},
            {"id": "s2", "action": "create_project", "params": created},
        ],
    }
    context = PageContext(dataset_id=project.dataset_id)
    text = "这些图要画行人框, 标签建好就开项目"
    assert match_recipe(text) is None
    result = model_plan(db, text, payload, context)
    assert result.kind == "plan"
    assert result.chain is not None
    assert result.chain.steps[1].params["name"] == "街景框"
