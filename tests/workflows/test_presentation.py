# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Keep bilingual step labels tied to frozen runs, including legacy definitions."""

import pytest
from pydantic import ValidationError

from datakeel.core.models import JsonDocument
from datakeel.core.workflow_models import WorkflowCreation, WorkflowStart, WorkflowStep
from datakeel.storage.database import Database
from datakeel.storage.workflow_store import create_run, get_run, list_runs
from datakeel.workflows.loader import list_workflows
from datakeel.workflows.models import OutputStep


def test_builtins_name_every_step_in_both_languages() -> None:
    """All built-in paths have useful titles rather than only internal node identifiers."""
    for workflow in list_workflows():
        for step in workflow.steps:
            assert step.title is not None
            assert step.title.zh != step.id
            assert step.title.en != step.id


@pytest.mark.parametrize("title", [{"zh": "完成"}, {"zh": "完成", "en": ""}])
def test_incomplete_step_titles_are_rejected(title: dict[str, str]) -> None:
    """An optional title, once supplied, must support either UI language."""
    with pytest.raises(ValidationError):
        OutputStep.model_validate({"id": "result", "type": "output", "value": 1, "title": title})


def test_run_titles_and_action_names_use_the_original_definition(db: Database) -> None:
    """Replay and history use the persisted title even after a caller edits its definition."""
    definition = JsonDocument(
        {
            "steps": [
                {
                    "id": "delete",
                    "type": "approval",
                    "title": {"zh": "签批删除", "en": "Approve deletion"},
                    "action": "delete_files",
                }
            ]
        }
    )
    creation = WorkflowCreation(
        workflow_id="example",
        definition=definition,
        request=WorkflowStart(idempotency_key="frozen-title"),
        steps=[WorkflowStep(id="delete", type="approval")],
    )
    run, _ = create_run(db, creation)
    changed = creation.model_copy(update={"definition": JsonDocument({"steps": []})})
    replay, created = create_run(db, changed)
    assert not created
    assert replay == get_run(db, run.id) == list_runs(db)[0]
    assert replay.steps[0].title is not None
    assert replay.steps[0].title.en == "Approve deletion"
    assert replay.steps[0].tool == "delete_files"


def test_legacy_steps_without_titles_remain_readable(db: Database) -> None:
    """Optional presentation metadata never prevents older stored runs from loading."""
    creation = WorkflowCreation(
        workflow_id="legacy",
        definition=JsonDocument({"steps": [{"id": "read", "tool": "get_quality"}]}),
        request=WorkflowStart(idempotency_key="legacy-title"),
        steps=[WorkflowStep(id="read", type="tool"), WorkflowStep(id="result", type="output")],
    )
    run, _ = create_run(db, creation)
    assert get_run(db, run.id).steps[0].title is None
    assert run.steps[0].tool == "get_quality"
    assert run.steps[1].tool is None
