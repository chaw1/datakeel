# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Golden evaluation executes the real runtime and persists measured comparisons."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
import yaml

from datakeel.agent.providers import FakeProvider
from datakeel.agent.service import send_message
from datakeel.core.errors import ValidationError
from datakeel.core.harness_eval import ExpectedAction, GoldenExpect, PlanOperation
from datakeel.harness.cases import load_cases
from datakeel.harness.evaluation import run_evaluation
from datakeel.harness.execution import run_case
from datakeel.harness.operations import apply_operation
from datakeel.harness.resources import contract_path
from datakeel.storage.harness_evaluations import list_evaluations

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

    from datakeel.agent.models import AgentEvent
    from datakeel.core.agent_models import MessageInput, Provider
    from datakeel.storage.database import Database


def test_twenty_real_golden_cases_pass_and_results_survive_restart(db: Database) -> None:
    """Run all scripted conversations twice and compare stored authoritative reports."""
    first = run_evaluation(db)
    assert first.total == first.passed == 20, [(case.id, case.failures) for case in first.cases]
    assert first.total_tokens > 0
    assert first.total_cost_usd > 0
    assert first.previous_id is None
    db.engine.dispose()
    second = run_evaluation(db)
    assert second.passed == 20
    assert second.previous_id == first.id
    assert second.previous_suite_digest == second.suite_digest
    assert second.passed_delta == 0
    assert second.token_delta == second.total_tokens - first.total_tokens
    assert second.cost_delta == second.total_cost_usd - first.total_cost_usd
    assert [report.id for report in list_evaluations(db)] == [second.id, first.id]


def test_every_expected_observation_can_make_a_golden_red() -> None:
    """Wrong tools, effects, context, answers, limits, and refusal claims must fail."""
    source = next(case for case in load_cases() if case.id == "03-reversible")
    expected = GoldenExpect(
        tool_sequence=[],
        tool_set=[],
        actions=[ExpectedAction(action_type="delete_files", requires_approval=False, executions=1)],
        answer_contains=["missing-answer"],
        answer_not_contains=["Quarantined"],
        stop_contains=["missing-stop"],
        context_contains=["missing-context"],
        operation_statuses=["SUCCEEDED"],
        operation_errors=["missing-error"],
        max_turns=0,
        max_tokens=0,
        file_count=0,
        quarantined_count=0,
    )
    result = run_case(source.model_copy(update={"expect": expected}), "fake")
    assert not result.passed
    assert len(result.failures) >= 13


def test_missing_plan_cannot_be_treated_as_a_successful_human_operation(db: Database) -> None:
    """A UI operation without a produced plan carries explicit missing evidence."""
    result = apply_operation(db, None, PlanOperation(operation="execute"))
    assert result.status == "MISSING_PLAN"
    assert result.error == "No plan was produced"


def test_case_loader_rejects_empty_and_duplicate_suites(tmp_path: Path) -> None:
    """Malformed suite structure fails before conversations begin."""
    with pytest.raises(ValidationError, match="No golden"):
        load_cases(tmp_path)
    case = load_cases()[0].model_dump(mode="json")
    for filename in ("first.yaml", "second.yaml"):
        (tmp_path / filename).write_text(yaml.safe_dump(case))
    with pytest.raises(ValidationError, match="unique"):
        load_cases(tmp_path)


def test_contracts_fall_back_to_bundled_wheel_resources(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Installed evaluation uses the same bundled contracts as a source checkout."""
    monkeypatch.setattr("datakeel.harness.resources.PACKAGE_ROOT", tmp_path / "datakeel")
    assert contract_path("golden") == tmp_path / "datakeel" / "_contracts" / "golden"


def test_explicit_provider_switch_uses_configuration_with_injected_offline_transport(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exercise real-provider configuration without opening a network connection."""
    source = load_cases()[0]
    fake = FakeProvider(source.turns[0].script)

    def offline_send(
        db: Database,
        identifier: str,
        message: MessageInput,
        *,
        provider: Provider | None = None,
    ) -> Iterator[AgentEvent]:
        assert provider is None
        return send_message(db, identifier, message, provider=fake)

    monkeypatch.setattr("datakeel.harness.execution.send_message", offline_send)
    result = run_case(source, "openai")
    assert result.passed
    assert fake.requests[0].model == "gpt-4.1-mini"
