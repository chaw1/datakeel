# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Show truthful question benchmark measurements without turning targets into command gates."""

from pathlib import Path

from rich.console import Console

from datakeel.harness.knowledge_evaluation import run_evaluation
from datakeel.storage.ask_evaluations import save_ask_evaluation
from datakeel.storage.database import Database


def evaluate_ask(db: Database, questions: Path | None = None, *, json_output: bool = False) -> None:
    """Persist an isolated benchmark and report thresholds without failure exit status."""
    report = save_ask_evaluation(db, run_evaluation(questions))
    console = Console()
    if json_output:
        console.print(
            report.model_dump_json(indent=2), markup=False, highlight=False, soft_wrap=True
        )
        return
    console.print(f"Ask accuracy: {report.correct}/{report.answerable} ({report.accuracy:.1%})")
    console.print(f"Refusal: {report.refused}/{report.unanswerable} ({report.refusal_rate:.1%})")
    console.print(f"Clarification: {report.clarified}/{report.clarification}")
    console.print(
        f"Evidence: {report.evidence_complete}/{len(report.questions)} ({report.evidence_rate:.1%})"
    )
    for question in report.questions:
        if not question.correct or not question.evidence_complete:
            console.print(
                f"{question.id}: status={question.actual_status}; correct={question.correct}; "
                f"evidence={question.evidence_complete}; error={question.error}",
                markup=False,
            )
    console.print(f"threshold_met={report.threshold_met}; report={report.id}")
    if report.knowledge is not None:
        for state in report.knowledge.states:
            console.print(f"Knowledge {state.state}: {state.passed}/{state.total}")
            for question in state.questions:
                if not question.passed:
                    console.print(f"{question.id}: {'; '.join(question.failures)}", markup=False)
        console.print(f"knowledge_threshold_met={report.knowledge.threshold_met}")
