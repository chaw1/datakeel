# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Protect fixed development and held-out cases through production question routing."""

import hashlib

import pytest

from datakeel.ask.service import ask_data
from datakeel.core.ask_models import AskRequest
from datakeel.storage.database import Database
from tests.ask.corpus_evaluation import evaluate_corpus
from tests.ask.corpus_fixture import build_corpus_fixture, patch_corpus_sources
from tests.ask.corpus_models import CorpusSplit, corpus_path, load_corpus


def test_corpus_partitions_preserve_independent_subjects_and_fixed_questions() -> None:
    """Guard the pre-implementation split, category sizes and untouched ground truth."""
    development, holdout = load_corpus("development"), load_corpus("holdout")
    combined = (*development.cases, *holdout.cases)
    assert sum(case.route == "knowledge" for case in combined) >= 200
    assert sum(case.route == "metric" for case in combined) >= 50
    development_subjects = {case.subject_id for case in development.cases}
    holdout_subjects = {case.subject_id for case in holdout.cases}
    assert development_subjects.isdisjoint(holdout_subjects)
    assert len(development_subjects | holdout_subjects) >= 12
    for corpus in (development, holdout):
        assert {case.position for case in corpus.cases} == {"start", "middle", "end"}
        for intent in ("owner", "upstream", "downstream", "owned"):
            assert {case.language for case in corpus.cases if case.intent == intent} == {
                "zh",
                "en",
            }
    assert hashlib.sha256(corpus_path("development").read_bytes()).hexdigest() == (
        "869e1d98839f69d9a3fc055508769c288b7046b764c22e2417fd9a30b9801a1a"
    )
    assert hashlib.sha256(corpus_path("holdout").read_bytes()).hexdigest() == (
        "d25498aade655924064793aecfc5777877f9e57cc036ee0c0e89eb9c40eb4729"
    )
    catalog_path = corpus_path("development").with_name("knowledge_corpus_catalog.json")
    assert hashlib.sha256(catalog_path.read_bytes()).hexdigest() == (
        "552138c24ac4439f5738f5876c23cf5cbcbe4a90aec4fe36b7505bee9c1b29b5"
    )


def test_corpus_fixture_exposes_numeric_leakage_when_value_execution_runs(
    db: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A registered metric produces a scalar, so knowledge leakage cannot hide in refusals."""
    fixture = build_corpus_fixture()
    patch_corpus_sources(db, monkeypatch, fixture)
    answer = ask_data(db, AskRequest(question="净成交额"))
    assert answer.answer_kind == "metric"
    assert answer.result is not None
    assert answer.result.rows == [[42]]


@pytest.mark.parametrize("split", ["development", "holdout"])
def test_independent_corpus_preserves_subjects_intents_and_numeric_route(
    db: Database, monkeypatch: pytest.MonkeyPatch, split: CorpusSplit
) -> None:
    """Require joint recognition and prohibit numeric answers to knowledge questions."""
    fixture = build_corpus_fixture()
    patch_corpus_sources(db, monkeypatch, fixture)
    report = evaluate_corpus(db, fixture, load_corpus(split))
    failed = tuple(item.case_id for item in report.results if not item.correct)
    required_accuracy = 1.0 if split == "development" else 0.9
    assert report.knowledge_correct / report.knowledge_total >= required_accuracy, failed
    assert report.knowledge_numeric == 0
    assert report.knowledge_metric_routes == 0
    assert report.metric_correct == report.metric_total, failed
