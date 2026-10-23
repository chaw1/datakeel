# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Real benchmark observations, honest thresholds, and independent persisted report types."""

from decimal import Decimal
from pathlib import Path

import pytest
import yaml

from datakeel.cli.evidence_benchmark import run_benchmark
from datakeel.core.errors import ValidationError
from datakeel.core.evidence_eval import EvidenceEvalReport
from datakeel.core.evidence_models import Assertion
from datakeel.core.harness_eval import EvalReport
from datakeel.core.models import AssetRef, new_id, utcnow
from datakeel.harness import evidence_evaluation
from datakeel.harness.evidence_evaluation import evaluate_evidence_dataset
from datakeel.harness.evidence_questions import load_evidence_questions
from datakeel.pipeline.evidence import evidence_pipeline
from datakeel.storage.database import Database
from datakeel.storage.evidence_evaluations import (
    list_evidence_evaluations,
    save_evidence_evaluation,
)
from datakeel.storage.evidence_store import list_assertions
from datakeel.storage.harness_evaluations import list_evaluations, save_evaluation
from datakeel.storage.task_queue import DatabaseQueue
from datakeel.worker.runner import execute


@pytest.fixture
def benchmark(db: Database, tmp_path: Path) -> EvidenceEvalReport:
    """Run the real extraction and fixed questions on a smaller generated corpus."""
    return run_benchmark(db, tmp_path / "samples", samples=100)


def test_pair_evaluation_when_peer_uses_other_version_cannot_match_source_gold(
    db: Database, tmp_path: Path, benchmark: EvidenceEvalReport, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Matching asset ids cannot turn a relationship from another revision into a true positive."""
    original = next(item for item in list_assertions(db) if item.predicate == "near_duplicate_of")
    assert isinstance(original.object, AssetRef)
    mismatched = original.model_copy(
        update={"object": original.object.model_copy(update={"version": "another-source-version"})}
    )

    def observations(_db: Database) -> list[Assertion]:
        return [mismatched]

    monkeypatch.setattr(evidence_evaluation, "list_assertions", observations)
    result = evaluate_evidence_dataset(
        db, benchmark.dataset_id, tmp_path / "samples/gold.json", benchmark.extraction.task_id
    )
    assert result.near_duplicate_pairs.selected == 0
    assert result.near_duplicate_pairs.true_positive == 0
    assert result.near_duplicate_pairs.recall == 0


def test_evaluation_when_real_extraction_runs_reports_actual_accounting_and_persists(
    db: Database, benchmark: EvidenceEvalReport
) -> None:
    """Keep the expected corrupt failure, direct-pair denominator, and measured question fields."""
    assert len(benchmark.questions) == 15
    assert benchmark.sample_count == 100
    assert benchmark.extraction_scope == "fresh"
    assert benchmark.extraction.inputs == 500
    assert benchmark.extraction.failed == 1
    assert benchmark.extraction.extracted == 499
    assert benchmark.extraction.skipped_cached == 0
    assert benchmark.extraction.elapsed_seconds > 0
    assert benchmark.evaluation_seconds > 0
    assert benchmark.benchmark_seconds is not None
    assert benchmark.near_duplicate_pairs.expected == 7
    assert benchmark.val_to_train_pairs.expected == 6
    assert benchmark.presence_counts.absent == 99
    assert benchmark.presence_counts.unknown > 0
    assert all(result.baseline_description for result in benchmark.questions)
    save_evidence_evaluation(db, benchmark)
    db.engine.dispose()
    assert list_evidence_evaluations(db) == [benchmark]
    assert list_evaluations(db) == []
    agent = EvalReport(
        id=new_id(),
        provider="fake",
        suite_digest="agent-suite",
        created_at=utcnow(),
        passed=0,
        total=0,
        cases=[],
        total_tokens=0,
        total_cost_usd=Decimal(0),
    )
    save_evaluation(db, agent)
    assert list_evaluations(db) == [agent]
    assert list_evidence_evaluations(db) == [benchmark]


def test_evaluation_when_threshold_is_unreachable_stores_false_and_cached_stats(
    db: Database, tmp_path: Path, benchmark: EvidenceEvalReport
) -> None:
    """A fresh evaluation of real cached output must not turn a missed threshold into success."""
    suite, _ = load_evidence_questions()
    payload = suite.model_dump(mode="json")
    payload["thresholds"]["recall_gain"] = 1
    questions = tmp_path / "strict.yaml"
    questions.write_text(yaml.safe_dump(payload), encoding="utf-8")
    queue = DatabaseQueue(db)
    task = queue.submit(benchmark.dataset_id, "cached-benchmark", evidence_pipeline())
    lease = queue.claim()
    assert lease is not None
    assert execute(queue, lease)
    report = evaluate_evidence_dataset(
        db, benchmark.dataset_id, tmp_path / "samples/gold.json", task, questions
    )
    assert not report.threshold_met
    assert report.extraction_scope == "existing"
    assert report.extraction.skipped_cached == report.extraction.inputs == 500
    assert report.extraction.extracted == 0
    save_evidence_evaluation(db, report)
    assert list_evidence_evaluations(db)[0].threshold_met is False


def test_evaluation_when_gold_or_extraction_mismatch_rejects_unverifiable_metrics(
    db: Database, tmp_path: Path, benchmark: EvidenceEvalReport
) -> None:
    """Never score an unrelated gold file or an uncompleted extraction as an evaluated corpus."""
    gold_path = tmp_path / "samples/gold.json"
    original = gold_path.read_text()
    gold_path.write_text(original.replace('"sample_count": 100', '"sample_count": 99'))
    with pytest.raises(ValidationError, match="Gold sample"):
        evaluate_evidence_dataset(db, benchmark.dataset_id, gold_path, benchmark.extraction.task_id)
    gold_path.write_text(original)
    queued = DatabaseQueue(db).submit(benchmark.dataset_id, "unfinished", evidence_pipeline())
    with pytest.raises(ValidationError, match="completed evidence task"):
        evaluate_evidence_dataset(db, benchmark.dataset_id, gold_path, queued)


def test_evaluation_when_query_limit_truncates_rejects_incomplete_metrics(
    db: Database, tmp_path: Path, benchmark: EvidenceEvalReport
) -> None:
    """A contract limit cannot silently shrink the actual candidate or gold denominator."""
    suite, _ = load_evidence_questions()
    payload = suite.model_dump(mode="json")
    payload["questions"][0]["baseline"]["limit"] = 1
    questions = tmp_path / "truncated.yaml"
    questions.write_text(yaml.safe_dump(payload), encoding="utf-8")
    with pytest.raises(ValidationError, match="truncated"):
        evaluate_evidence_dataset(
            db,
            benchmark.dataset_id,
            tmp_path / "samples/gold.json",
            benchmark.extraction.task_id,
            questions,
        )
