# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Mutation test reports must prove the declared assertion failed in a strictly local run."""

from __future__ import annotations

import subprocess
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest

from datakeel.core.harness_eval import EvalCaseResult, EvalReport, ObservedToolResult
from datakeel.core.models import JsonDocument, utcnow
from scripts import mutate

if TYPE_CHECKING:
    from pathlib import Path


@pytest.mark.parametrize(
    ("code", "body", "error"),
    [
        (2, "", "process crashed"),
        (1, '<testcase name="target" classname="tests.test_target"><error/></testcase>', "outcome"),
        (
            1,
            '<testcase name="wrong" classname="tests.test_target"><failure/></testcase>',
            "declared",
        ),
        (
            1,
            (
                '<testcase name="target" classname="tests.test_target">'
                "<failure>RuntimeError: broke</failure></testcase>"
            ),
            "outside its assertion",
        ),
    ],
)
def test_test_runner_when_crash_setup_or_wrong_case_occurs_never_counts_kill(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, code: int, body: str, error: str
) -> None:
    """A process exit or unrelated failure cannot masquerade as the designated mutant kill."""

    def process(
        command: list[str],
        **kwargs: object,
    ) -> subprocess.CompletedProcess[str]:
        (tmp_path / "test-results.xml").write_text(
            f"<testsuites><testsuite>{body}</testsuite></testsuites>"
        )
        return subprocess.CompletedProcess(command, code, stdout="", stderr="fixture process")

    monkeypatch.setattr(mutate.subprocess, "run", process)
    with pytest.raises(RuntimeError, match=error):
        mutate.evaluate_image_test(tmp_path, "tests/test_target.py::target")


def test_mutation_environment_when_remote_settings_present_uses_only_local_targets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Inherited object storage, provider endpoints, and cloud credentials cannot reach a mutant."""
    for name in (
        "DATAKEEL_S3_BUCKET",
        "DATAKEEL_S3_ENDPOINT",
        "DATAKEEL_S3_ACCESS",
        "DATAKEEL_S3_SECRET",
        "DATAKEEL_LLM_URL",
        "DATAKEEL_TEST_DATABASE_URL",
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
    ):
        monkeypatch.setenv(name, "synthetic-external-setting")
    environment = mutate.local_environment(tmp_path)
    assert not any(key.startswith(("DATAKEEL_S3_", "AWS_")) for key in environment)
    assert "DATAKEEL_LLM_URL" not in environment
    assert "DATAKEEL_TEST_DATABASE_URL" not in environment
    assert environment["DATAKEEL_HOME"] == str(tmp_path / "home")
    assert environment["DATAKEEL_DATABASE_URL"] == f"sqlite:///{tmp_path / 'evaluation.db'}"


@pytest.fixture
def explanation_result() -> EvalCaseResult:
    """Represent the measured schema failure produced by an actually returned wrong state."""
    return EvalCaseResult(
        id="14-evidence-unknown",
        passed=False,
        failures=["Tool content mismatch: explain_sample at data.states: unknown missing"],
        tool_sequence=["explain_sample"],
        action_types=[],
        operations=[],
        final_answer="The label gap is unknown.",
        stop_reasons=[],
        turns=2,
        tokens=100,
        cost_usd=Decimal(0),
        tool_results=[
            ObservedToolResult(
                name="explain_sample",
                status="SUCCEEDED",
                content=JsonDocument(root={"data": {"states": [{"value": "absent"}]}}),
                asset_refs=[],
            )
        ],
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"passed": True},
        {"fixture_error": "Extraction failed before any tool"},
        {"tool_sequence": []},
        {"tool_results": []},
        {"failures": ["Answer missing: unknown"]},
        {"failures": ["Tool content mismatch: query_evidence at data.states: unknown missing"]},
    ],
)
def test_explanation_probe_when_no_measured_state_assertion_fails_never_counts_kill(
    explanation_result: EvalCaseResult, changes: dict[str, object]
) -> None:
    """Fixture errors, scripted text, and unrelated failed calls cannot satisfy the deeper check."""
    assert not mutate.explanation_failure(1, explanation_result.model_copy(update=changes))


def test_explanation_probe_when_tool_failed_or_process_crashed_never_counts_kill(
    explanation_result: EvalCaseResult,
) -> None:
    """Require a successful actual tool result and the normal failed-golden exit code."""
    assert not mutate.explanation_failure(2, explanation_result)
    failed_tool = explanation_result.tool_results[0].model_copy(update={"status": "FAILED"})
    assert not mutate.explanation_failure(
        1, explanation_result.model_copy(update={"tool_results": [failed_tool]})
    )


def _report(case: EvalCaseResult) -> EvalReport:
    return EvalReport(
        id="measured-report",
        provider="fake",
        suite_digest="fixture",
        created_at=utcnow(),
        passed=0,
        total=1,
        cases=[case],
        total_tokens=case.tokens,
        total_cost_usd=case.cost_usd,
    )


def test_unknown_mutation_when_boundary_and_explanation_fail_records_both_separately(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, explanation_result: EvalCaseResult
) -> None:
    """Bypass only the temporary copy after proving the unmodified production guard rejected it."""
    mutation = next(item for item in mutate.MUTATIONS if item.name == "missing-annotation-unknown")
    boundary = explanation_result.model_copy(
        update={
            "tool_sequence": [],
            "tool_results": [],
            "fixture_error": "Only directly measured corruption may assert absence",
        }
    )
    target = tmp_path / "datakeel/core/evidence_models.py"
    target.parent.mkdir(parents=True)
    target.write_text('elif self.object.value == "absent" and self.predicate != "corrupt":')

    def evaluate(_directory: Path) -> tuple[int, EvalReport]:
        return 1, _report(explanation_result)

    monkeypatch.setattr(mutate, "_evaluate", evaluate)
    result = mutate.measure_unknown_mutation(mutation, tmp_path, 1, _report(boundary))
    assert result.killed
    assert result.boundary_case == boundary
    assert result.explanation_case == explanation_result
    assert result.explanation_probe_exit == 1
    assert result.validation_bypass is not None
    assert 'not in {"corrupt", "label_gap"}' in target.read_text()


def test_unknown_mutation_when_fixture_fails_unexpectedly_never_bypasses_or_counts_kill(
    tmp_path: Path, explanation_result: EvalCaseResult
) -> None:
    """An unrelated setup failure remains a surviving mutant without any deep probe."""
    mutation = next(item for item in mutate.MUTATIONS if item.name == "missing-annotation-unknown")
    boundary = explanation_result.model_copy(
        update={"tool_sequence": [], "tool_results": [], "fixture_error": "Missing fixture file"}
    )
    result = mutate.measure_unknown_mutation(mutation, tmp_path, 1, _report(boundary))
    assert not result.killed
    assert result.explanation_case is None
    assert result.validation_bypass is None
