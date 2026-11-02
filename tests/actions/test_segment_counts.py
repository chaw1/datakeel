# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""FIX1 controlled-action regression for segment-only min/max counting."""

from collections.abc import Callable, Mapping

from datakeel.actions.execution import execute_plan
from datakeel.actions.models import ActionContext, ActionRun, ExecuteRequest
from datakeel.actions.planning import prepare_action
from datakeel.core.annotation_models import AnnotationRecord
from datakeel.core.errors import ValidationError
from datakeel.core.models import JsonDocument, new_id
from datakeel.core.production_models import ProductionTask
from datakeel.storage.database import Database
from tests.storage.test_production_segments import (
    segment_annotation,
    segment_project,
    segment_source,
)


def _reject(call: Callable[[], object], match: str) -> None:
    message = None
    try:
        call()
    except ValidationError as error:
        message = str(error)
    assert message is not None, "Expected segment action validation to reject the operation"
    assert match in message


def _run(db: Database, action: str, values: Mapping[str, object]) -> ActionRun:
    plan = prepare_action(
        db,
        action,
        JsonDocument.model_validate({"request_id": new_id(), **values}),
        ActionContext(actor="local"),
    )
    return execute_plan(db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest, actor="local"))


def _save(db: Database, task_id: str, annotation: AnnotationRecord) -> ActionRun:
    return _run(
        db,
        "save_revision",
        {
            "task_id": task_id,
            "previous_revision_id": None,
            "annotation": annotation.model_dump(mode="json"),
        },
    )


def test_action_max_one_allows_one_segment_with_classification(db: Database) -> None:
    """The controlled save and submit actions accept the FIX1 max-one reproduction."""
    segment_source(db)
    _, tasks = segment_project(db, rules={"min_annotations": 1, "max_annotations": 1})
    annotation = segment_annotation(tasks[0]).model_copy(
        update={"labels": ("a",), "segments": (segment_annotation(tasks[0]).segments or ())[:1]}
    )
    try:
        saved = _save(db, tasks[0].id, annotation)
        submitted = _run(db, "submit_task", {"task_id": tasks[0].id})
    except ValidationError as error:
        message = "FIX1 max-one actions must succeed"
        raise AssertionError(message) from error
    assert saved.status == "SUCCEEDED"
    assert submitted.status == "SUCCEEDED"
    assert submitted.receipt is not None
    assert ProductionTask.model_validate(submitted.receipt.quality["details"]).state == "approved"


def test_action_min_two_rejects_one_segment_with_classification(db: Database) -> None:
    """The controlled save action rejects the FIX1 min-two reproduction."""
    segment_source(db)
    _, tasks = segment_project(db, rules={"min_annotations": 2, "max_annotations": 5})
    annotation = segment_annotation(tasks[0]).model_copy(
        update={"labels": ("a",), "segments": (segment_annotation(tasks[0]).segments or ())[:1]}
    )
    _reject(lambda: _save(db, tasks[0].id, annotation), "count")
