# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Evaluate graph questions in isolated initial and reviewed production fixtures."""

from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from time import monotonic
from typing import Literal

from datakeel.ask.evaluation import run_evaluation as run_metric_evaluation
from datakeel.ask.service import ask_data
from datakeel.core.ask_eval import AskEvalReport
from datakeel.core.ask_models import AskRequest
from datakeel.core.errors import DatakeelError
from datakeel.core.knowledge_eval import (
    KnowledgeEvaluation,
    KnowledgeQuestionResult,
    KnowledgeQuestionSet,
    KnowledgeStateResult,
)
from datakeel.harness.enterprise_kg import seed_enterprise_kg
from datakeel.harness.enterprise_reviews import review_enterprise_kg
from datakeel.harness.knowledge_checks import knowledge_failures
from datakeel.harness.resources import contract_path
from datakeel.kg.loader import load_contract
from datakeel.sample_enterprise import EnterpriseGold
from datakeel.storage.database import Database


def _state_result(
    db: Database,
    suite: KnowledgeQuestionSet,
    gold: EnterpriseGold,
    state: Literal["initial", "reviewed"],
) -> KnowledgeStateResult:
    results: list[KnowledgeQuestionResult] = []
    for question in suite.questions:
        expected = (
            question.reviewed if state == "reviewed" and question.reviewed else question.initial
        )
        try:
            answer = ask_data(
                db,
                AskRequest(
                    question=question.question,
                    reference_instant=suite.reference_instant,
                ),
            )
            failures = knowledge_failures(
                expected, answer, gold.answers.get(expected.gold_key or "")
            )
            results.append(
                KnowledgeQuestionResult(
                    id=question.id,
                    question=question.question,
                    passed=not failures,
                    failures=failures,
                    answer=answer,
                )
            )
        except DatakeelError as error:
            results.append(
                KnowledgeQuestionResult(
                    id=question.id,
                    question=question.question,
                    passed=False,
                    failures=(f"{type(error).__name__}: {error}",),
                )
            )
    return KnowledgeStateResult(
        state=state,
        total=len(results),
        passed=sum(item.passed for item in results),
        questions=tuple(results),
        suite_digest=sha256(suite.model_dump_json().encode()).hexdigest(),
    )


def run_knowledge_evaluation() -> KnowledgeEvaluation:
    """Replay both review states, including relinking then same-version extraction."""
    started = monotonic()
    suite = load_contract(contract_path("ask/knowledge.yaml"), KnowledgeQuestionSet)
    with TemporaryDirectory(prefix="datakeel-knowledge-eval-") as temporary:
        directory = Path(temporary)
        db = Database(f"sqlite:///{directory / 'knowledge.sqlite'}")
        db.migrate()
        try:
            fixture = seed_enterprise_kg(db, directory)
            gold = EnterpriseGold.model_validate_json(
                (directory / "enterprise/gold.json").read_text()
            )
            initial = _state_result(db, suite, gold, "initial")
            review_enterprise_kg(db, fixture)
            reviewed = _state_result(db, suite, gold, "reviewed")
            return KnowledgeEvaluation(
                states=(initial, reviewed),
                threshold_met=all(item.passed == item.total for item in (initial, reviewed)),
                elapsed_seconds=monotonic() - started,
            )
        finally:
            db.engine.dispose()


def run_evaluation(questions: Path | None = None) -> AskEvalReport:
    """Keep all original metric statistics intact and append a separate knowledge report."""
    metric = run_metric_evaluation(questions)
    return metric.model_copy(update={"knowledge": run_knowledge_evaluation()})
