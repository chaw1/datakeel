# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Evaluate independent language partitions through the real question service."""

import argparse
import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import cast

import pytest

from datakeel.ask.service import ask_data
from datakeel.core.ask_models import AskRequest
from datakeel.storage.database import Database
from tests.ask.corpus_fixture import build_corpus_fixture, patch_corpus_sources
from tests.ask.corpus_models import (
    CorpusCase,
    CorpusFixture,
    CorpusReport,
    CorpusResult,
    CorpusSplit,
    QuestionCorpus,
    corpus_path,
    load_corpus,
)


def _evaluate_case(db: Database, fixture: CorpusFixture, case: CorpusCase) -> CorpusResult:
    answer = ask_data(db, AskRequest(question=case.question))
    knowledge = answer.knowledge if answer.answer_kind == "knowledge" else None
    subject = knowledge.subject if knowledge else None
    actual_id = subject.asset_ref.asset_id if subject else None
    expected = next(item for item in fixture.catalog.subjects if item.id == case.subject_id)
    correct = answer.answer_kind == case.route
    if case.route == "knowledge":
        correct = (
            correct
            and actual_id == expected.asset_id
            and bool(knowledge and knowledge.intent == case.intent)
        )
    return CorpusResult(
        case_id=case.id,
        expected_route=case.route,
        actual_route=answer.answer_kind,
        expected_intent=case.intent,
        actual_intent=knowledge.intent if knowledge else None,
        expected_subject=expected.asset_id,
        actual_subject=actual_id,
        numeric_result=answer.result is not None,
        correct=correct,
    )


def evaluate_corpus(db: Database, fixture: CorpusFixture, corpus: QuestionCorpus) -> CorpusReport:
    """Keep intent accuracy, numeric leakage and metric routing as separate scores."""
    results = tuple(_evaluate_case(db, fixture, case) for case in corpus.cases)
    knowledge = tuple(item for item in results if item.expected_route == "knowledge")
    metrics = tuple(item for item in results if item.expected_route == "metric")
    return CorpusReport(
        split=corpus.split,
        corpus_sha256=hashlib.sha256(corpus_path(corpus.split).read_bytes()).hexdigest(),
        knowledge_total=len(knowledge),
        knowledge_correct=sum(item.correct for item in knowledge),
        knowledge_numeric=sum(item.numeric_result for item in knowledge),
        knowledge_metric_routes=sum(item.actual_route == "metric" for item in knowledge),
        metric_total=len(metrics),
        metric_correct=sum(item.correct for item in metrics),
        results=results,
    )


def main() -> None:
    """Write a complete local receipt without printing held-out question text."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", required=True, choices=("development", "holdout"))
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    split, output = cast("CorpusSplit", args.split), cast("Path", args.output)
    fixture = build_corpus_fixture()
    with (
        TemporaryDirectory(prefix="question-corpus-") as directory,
        pytest.MonkeyPatch.context() as patch,
    ):
        db = Database(f"sqlite:///{Path(directory) / 'corpus.db'}")
        try:
            db.migrate()
            patch_corpus_sources(db, patch, fixture)
            report = evaluate_corpus(db, fixture, load_corpus(split))
        finally:
            db.engine.dispose()
    output.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
