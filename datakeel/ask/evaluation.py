# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Run an isolated deterministic enterprise benchmark against independent generated gold."""

from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from time import monotonic

import yaml
from pydantic import ValidationError as ModelValidationError

from datakeel.ask.evaluation_checks import complete_evidence, correct_answer
from datakeel.ask.service import ask_data
from datakeel.catalog.service import import_catalog
from datakeel.core.ask_eval import (
    AskEvalReport,
    AskQuestion,
    AskQuestionResult,
    AskQuestionSet,
    AskThresholds,
)
from datakeel.core.ask_models import AskRequest
from datakeel.core.catalog_models import CatalogImportRequest
from datakeel.core.errors import DatakeelError, ValidationError
from datakeel.metrics.loader import load_layer
from datakeel.sample_enterprise import EnterpriseGold, generate_enterprise
from datakeel.storage.database import Database
from datakeel.storage.metric_store import install_layer

PACKAGE_ROOT = Path(__file__).resolve().parents[1]


def contract_path(name: str) -> Path:
    """Locate the same semantic fixtures in a checkout or an installed wheel."""
    source = PACKAGE_ROOT.parent / "contracts" / name
    return source if source.exists() else PACKAGE_ROOT / "_contracts" / name


def load_questions(path: Path | None = None) -> AskQuestionSet:
    """Validate a complete question suite before creating any benchmark source."""
    try:
        return AskQuestionSet.model_validate(
            yaml.safe_load((path or contract_path("ask/questions.yaml")).read_text())
        )
    except (OSError, yaml.YAMLError, ModelValidationError) as exc:
        msg = f"Invalid question benchmark: {exc}"
        raise ValidationError(msg) from exc


def _seed(db: Database, directory: Path) -> EnterpriseGold:
    sample = generate_enterprise(directory / "sources")
    for source in sample.sources:
        import_catalog(
            db,
            CatalogImportRequest(
                source_id=source.id, name=source.name, connection_url=f"sqlite:///{source.path}"
            ),
        )
    install_layer(db, load_layer(contract_path("semantic-layer")))
    return EnterpriseGold.model_validate_json(sample.gold_path.read_text())


def _question(
    db: Database, question: AskQuestion, suite: AskQuestionSet, gold: EnterpriseGold
) -> AskQuestionResult:
    expected = gold.answers.get(question.gold_key or "")
    try:
        if question.gold_key is not None and expected is None:
            msg = f"Independent gold key not found: {question.gold_key}"
            raise ValidationError(msg)
        answer = ask_data(
            db, AskRequest(question=question.question, reference_instant=suite.reference_instant)
        )
    except DatakeelError as exc:
        return AskQuestionResult(
            id=question.id,
            expected_status=question.expected_status,
            actual_status="error",
            correct=False,
            evidence_complete=False,
            expected_value=expected,
            error=f"{type(exc).__name__}: {exc}",
        )
    return AskQuestionResult(
        id=question.id,
        expected_status=question.expected_status,
        actual_status=answer.status,
        correct=correct_answer(question, answer, expected),
        evidence_complete=complete_evidence(answer),
        expected_value=expected,
        answer=answer,
    )


def _report(
    suite: AskQuestionSet,
    gold: EnterpriseGold,
    results: tuple[AskQuestionResult, ...],
    elapsed: float,
) -> AskEvalReport:
    counts = {
        status: [item for item in results if item.expected_status == status]
        for status in ("answered", "unanswerable", "clarification")
    }
    correct = sum(item.correct for item in counts["answered"])
    refused = sum(
        item.actual_status == "unanswerable" and item.correct for item in counts["unanswerable"]
    )
    evidence = sum(item.evidence_complete for item in results)
    thresholds = AskThresholds()
    return AskEvalReport(
        reference_instant=suite.reference_instant,
        suite_digest=sha256(suite.model_dump_json().encode()).hexdigest(),
        gold_digest=sha256(gold.model_dump_json().encode()).hexdigest(),
        questions=results,
        answerable=len(counts["answered"]),
        correct=correct,
        accuracy=correct / len(counts["answered"]) if counts["answered"] else 0,
        unanswerable=len(counts["unanswerable"]),
        refused=refused,
        refusal_rate=refused / len(counts["unanswerable"]) if counts["unanswerable"] else 0,
        clarification=len(counts["clarification"]),
        clarified=sum(item.correct for item in counts["clarification"]),
        evidence_complete=evidence,
        evidence_rate=evidence / len(results),
        thresholds=thresholds,
        threshold_met=(
            correct >= thresholds.minimum_correct
            and refused >= thresholds.required_refusals
            and evidence >= thresholds.required_evidence
            and evidence == len(results)
            and refused == len(counts["unanswerable"])
        ),
        evaluation_seconds=elapsed,
    )


def run_evaluation(questions: Path | None = None) -> AskEvalReport:
    """Generate fresh sources and report measurements without using caller settings or models."""
    suite = load_questions(questions)
    started = monotonic()
    with TemporaryDirectory(prefix="datakeel-ask-eval-") as temporary:
        directory = Path(temporary)
        db = Database(f"sqlite:///{directory / 'benchmark.sqlite'}")
        db.migrate()
        try:
            gold = _seed(db, directory)
            results = tuple(_question(db, item, suite, gold) for item in suite.questions)
            return _report(suite, gold, results, monotonic() - started)
        finally:
            db.engine.dispose()
