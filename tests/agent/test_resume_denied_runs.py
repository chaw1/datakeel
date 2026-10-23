# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Rejected legacy attempts never masquerade as an already executed approved action."""

from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING

import pytest

from datakeel.actions.models import ApprovalDecision, ExecuteRequest
from datakeel.actions.service import approve_plan, execute_plan, list_runs
from datakeel.agent.providers import FakeProvider
from datakeel.agent.service import get_conversation, resume_conversation
from datakeel.core.agent_models import ModelResponse, ResumeInput
from datakeel.core.errors import AuthorizationError, ConflictError
from datakeel.storage.dataset_service import list_files
from datakeel.storage.tool_invocations import list_invocations
from tests.agent.test_resume import pause_deletion

if TYPE_CHECKING:
    from datakeel.storage.database import Database
    from datakeel.storage.views import DatasetView


def test_resume_when_legacy_execution_was_denied_performs_the_later_approved_action(
    db: Database,
    dataset: DatasetView,
) -> None:
    """An unauthorised UI attempt is retained as audit without blocking a later signed resume."""
    conversation_id, plan = pause_deletion(db, dataset.id)
    with pytest.raises(AuthorizationError, match="explicit human approval"):
        execute_plan(db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest))
    denied = list_runs(db)[0]
    assert denied.status == "DENIED"
    assert len(list_files(db, dataset.id)) == 2
    approve_plan(db, plan.id, ApprovalDecision(approve=True, plan_digest=plan.plan_digest))
    events = list(
        resume_conversation(
            db,
            conversation_id,
            ResumeInput(plan_id=plan.id, idempotency_key="after-legacy-denial"),
            provider=FakeProvider([ModelResponse(content="Approved action completed.")]),
        )
    )
    receipt = next(
        event.outcome.run for event in events if event.event == "receipt" and event.outcome
    )
    assert receipt is not None
    assert receipt.status == "SUCCEEDED"
    assert receipt.id != denied.id
    assert Counter(run.status for run in list_runs(db)) == {"DENIED": 1, "SUCCEEDED": 1}
    assert len(list_files(db, dataset.id)) == 1
    assert [event.event for event in events] == ["receipt", "text", "done"]


def test_resume_when_latest_legacy_retry_was_denied_reuses_the_successful_ui_run(
    db: Database,
    dataset: DatasetView,
) -> None:
    """A later rejected retry cannot replace the original successful receipt during recovery."""
    conversation_id, plan = pause_deletion(db, dataset.id)
    approve_plan(db, plan.id, ApprovalDecision(approve=True, plan_digest=plan.plan_digest))
    request = ExecuteRequest(plan_digest=plan.plan_digest)
    original = execute_plan(db, plan.id, request)
    with pytest.raises(ConflictError, match="already executed"):
        execute_plan(db, plan.id, request)
    before = list_runs(db)
    assert [run.status for run in before] == ["DENIED", "SUCCEEDED"]
    invocations = list_invocations(db, conversation_id)
    provider = FakeProvider([ModelResponse(content="Original receipt recovered.")])
    events = list(
        resume_conversation(
            db,
            conversation_id,
            ResumeInput(plan_id=plan.id, idempotency_key="after-rejected-retry"),
            provider=provider,
        )
    )
    receipt = next(
        event.outcome.run for event in events if event.event == "receipt" and event.outcome
    )
    assert receipt == original
    assert list_runs(db) == before
    assert list_invocations(db, conversation_id) == invocations
    assert len(list_files(db, dataset.id)) == 1
    assert [event.event for event in events] == ["receipt", "text", "done"]
    view = get_conversation(db, conversation_id)
    card = next(event.outcome for event in view.events if event.event == "plan")
    assert card is not None
    assert card.run == original
    assert original.id in provider.requests[0].messages[-1].content
    assert before[0].id not in provider.requests[0].messages[-1].content
