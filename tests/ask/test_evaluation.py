# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Measure independent generated answers and persist truthful, non-gating benchmark reports."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
import yaml
from pydantic import ValidationError as ModelValidationError

from datakeel.ask.evaluation import contract_path, load_questions, run_evaluation
from datakeel.ask.evaluation_checks import (
    complete_evidence,
    correct_answer,
    scalar_equal,
    table_equal,
)
from datakeel.cli.ask_evaluation import evaluate_ask
from datakeel.core.ask_eval import AskQuestion, AskQuestionSet
from datakeel.core.errors import ValidationError
from datakeel.core.metric_models import QueryResult
from datakeel.storage.ask_evaluations import list_ask_evaluations, save_ask_evaluation
from datakeel.storage.harness_evaluations import list_evaluations

if TYPE_CHECKING:
    from pathlib import Path

    from datakeel.core.ask_eval import AskEvalReport
    from datakeel.storage.database import Database


@pytest.fixture(scope="module")
def report() -> AskEvalReport:
    """Run the actual 20-question pipeline against fresh, independently generated gold."""
    return run_evaluation()


def test_twenty_questions_match_independent_gold_with_complete_evidence(
    report: AskEvalReport,
) -> None:
    """Every default status, scalar, and persisted evidence must survive real execution."""
    assert report.correct == report.answerable == 14
    assert report.refused == report.unanswerable == 4
    assert report.clarified == report.clarification == 2
    assert report.evidence_complete == len(report.questions) == 20
    assert report.threshold_met
    assert report.evaluation_seconds > 0
    assert len(report.suite_digest) == len(report.gold_digest) == 64
    first = report.questions[0]
    assert first.expected_value == 4979475
    assert first.answer is not None
    assert first.answer.result is not None
    assert first.answer.result.rows == [[4979475]]


def test_ask_report_is_persisted_separately_from_agent_reports(
    db: Database, report: AskEvalReport
) -> None:
    """Report decoding remains provider-specific after restarting the database handle."""
    assert save_ask_evaluation(db, report) == report
    db.engine.dispose()
    assert list_ask_evaluations(db) == [report]
    assert list_evaluations(db) == []


def test_cli_reports_failed_threshold_without_nonzero_exit(
    db: Database, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """An unmet accuracy target is measured, printed, and saved without a success claim."""
    suite = load_questions()
    question = suite.questions[0].model_copy(update={"gold_key": "missing-independent-gold"})
    path = tmp_path / "questions.yaml"
    path.write_text(
        yaml.safe_dump(suite.model_copy(update={"questions": (question,)}).model_dump(mode="json"))
    )
    evaluate_ask(db, path)
    output = capsys.readouterr().out
    assert "threshold_met=False" in output
    assert "missing-independent-gold" in output
    assert list_ask_evaluations(db)[0].questions[0].actual_status == "error"
    evaluate_ask(db, path, json_output=True)
    assert '"threshold_met": false' in capsys.readouterr().out


def test_missing_or_invalid_suites_fail_before_execution(tmp_path: Path) -> None:
    """Unreadable YAML and structurally invalid contracts have a typed validation error."""
    path = tmp_path / "questions.yaml"
    with pytest.raises(ValidationError, match="Invalid question"):
        load_questions(path)
    path.write_text("questions: [")
    with pytest.raises(ValidationError, match="Invalid question"):
        load_questions(path)
    path.write_text("questions: []")
    with pytest.raises(ValidationError, match="Invalid question"):
        load_questions(path)


def test_question_models_reject_missing_gold_duplicate_ids_and_excess_tables() -> None:
    """Benchmark declarations cannot silently change denominators or expected answer kinds."""
    with pytest.raises(ModelValidationError, match="exactly one"):
        AskQuestion(id="a", question="收入", expected_status="answered")
    suite = load_questions()
    with pytest.raises(ModelValidationError, match="unique"):
        AskQuestionSet(
            reference_instant=suite.reference_instant, questions=(suite.questions[0],) * 2
        )
    table = QueryResult(columns=["value"], rows=[[1]])
    items = tuple(
        AskQuestion(
            id=str(i),
            question="收入",
            expected_status="answered",
            metric_id="revenue",
            expected_table=table,
        )
        for i in range(3)
    )
    with pytest.raises(ModelValidationError, match="at most two"):
        AskQuestionSet(reference_instant=suite.reference_instant, questions=items)


def test_bundled_question_contract_location(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Wheel installations resolve the same embedded question contract without cwd assumptions."""
    monkeypatch.setattr("datakeel.ask.evaluation.PACKAGE_ROOT", tmp_path / "datakeel")
    assert (
        contract_path("ask/questions.yaml") == tmp_path / "datakeel/_contracts/ask/questions.yaml"
    )


def test_numeric_tolerance_and_table_multisets_preserve_duplicate_counts() -> None:
    """Half-percent tolerance never masks wrong text, missing duplicates, or truncated results."""
    assert scalar_equal(100.4, 100)
    assert not scalar_equal(101, 100)
    assert scalar_equal("east", "east")
    assert not scalar_equal("east", "west")
    expected = QueryResult(columns=["region", "amount"], rows=[["east", 100], ["east", 100]])
    assert table_equal(expected, expected)
    for changed in [
        expected.model_copy(update={"columns": ["wrong"]}),
        expected.model_copy(update={"rows": [["east", 100]]}),
        expected.model_copy(update={"truncated": True}),
        expected.model_copy(update={"rows": [["east", 100], ["west", 100]]}),
    ]:
        assert not table_equal(changed, expected)


def test_correctness_checks_do_not_trust_status_or_result_shape_alone(
    report: AskEvalReport,
) -> None:
    """The measured answer must have the requested metric and matching scalar or table gold."""
    answer = report.questions[0].answer
    assert answer is not None
    assert answer.result is not None
    question = load_questions().questions[0]
    assert not correct_answer(
        question.model_copy(update={"expected_status": "unanswerable"}), answer, 4979475
    )
    assert not correct_answer(question.model_copy(update={"metric_id": "wrong"}), answer, 4979475)
    assert not correct_answer(question, answer.model_copy(update={"metric_card": None}), 4979475)
    assert not correct_answer(question, answer.model_copy(update={"result": None}), 4979475)
    assert not correct_answer(question, answer, None)
    assert not correct_answer(
        question, answer.model_copy(update={"result": QueryResult(columns=[], rows=[])}), 4979475
    )
    table_question = question.model_copy(update={"gold_key": None, "expected_table": answer.result})
    assert correct_answer(table_question, answer, None)


def test_evidence_measurement_rejects_missing_provenance_or_nonselect_sql(
    report: AskEvalReport,
) -> None:
    """Missing persisted assertions and corrupted answer evidence never count as complete."""
    answer = report.questions[0].answer
    assert answer is not None
    assert answer.sql is not None
    assert not complete_evidence(answer.model_copy(update={"assertion_ids": ()}))
    assert not complete_evidence(answer.model_copy(update={"metric_card": None}))
    assert not complete_evidence(answer.model_copy(update={"sql": None}))
    assert not complete_evidence(
        answer.model_copy(
            update={"sql": answer.sql.model_copy(update={"sql": "DELETE FROM orders"})}
        )
    )
