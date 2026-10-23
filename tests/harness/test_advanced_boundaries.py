# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Extended golden formats prove actual session and billing boundaries, not scripted prose."""

from __future__ import annotations

from typing import TYPE_CHECKING

from datakeel.agent.service import create_conversation
from datakeel.core.harness_eval import GoldenExpect
from datakeel.harness.cases import load_cases
from datakeel.harness.execution import run_case
from datakeel.storage.harness_service import list_traces

if TYPE_CHECKING:
    import pytest

    from datakeel.agent.models import ConversationView
    from datakeel.core.agent_models import ConversationCreate
    from datakeel.core.harness_models import ModelCallTrace
    from datakeel.storage.database import Database


def test_cross_session_golden_creates_distinct_root_conversations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The memory scenario must actually leave its first transcript before retrieving memory."""
    created: list[ConversationView] = []

    def capture(db: Database, request: ConversationCreate) -> ConversationView:
        result = create_conversation(db, request)
        created.append(result)
        return result

    monkeypatch.setattr("datakeel.harness.execution.create_conversation", capture)
    case = next(case for case in load_cases() if case.id == "29-memory-cross-session")
    result = run_case(case, "fake")
    assert result.passed, result.failures
    assert len(created) == 2
    assert created[0].id != created[1].id
    assert created[0].config.dataset_id == created[1].config.dataset_id


def test_delegation_golden_counts_root_turns_and_every_child_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Parent turn ceilings and complete cost measurements use different trace projections."""
    observed: list[ModelCallTrace] = []

    def capture(db: Database, conversation_id: str | None = None) -> list[ModelCallTrace]:
        traces = list_traces(db, conversation_id)
        observed.extend(traces)
        return traces

    monkeypatch.setattr("datakeel.harness.execution.list_traces", capture)
    case = next(case for case in load_cases() if case.id == "21-delegation-catalog")
    result = run_case(case, "fake")
    assert result.passed, result.failures
    assert len(observed) == 5
    assert result.turns == sum(trace.depth == 0 for trace in observed) == 3
    assert result.tokens == sum(
        trace.usage.input_tokens + trace.usage.output_tokens for trace in observed
    )
    assert sum(trace.accounted_tokens for trace in observed if trace.depth) > 0


def test_child_label_mismatch_cannot_pass_with_permissive_stop_expectation() -> None:
    """Verify child script ownership even when the expected stop permits provider errors."""
    case = next(case for case in load_cases() if case.id == "21-delegation-catalog")
    script = list(case.turns[0].script)
    script[2] = script[2].model_copy(update={"agent": "main"})
    changed = case.model_copy(
        update={
            "turns": [case.turns[0].model_copy(update={"script": script})],
            "expect": GoldenExpect(stop_contains=["provider_error"], max_tokens=200000),
        }
    )
    result = run_case(changed, "fake")
    assert not result.passed
    assert any("consumed by catalog-analyst" in failure for failure in result.failures)
