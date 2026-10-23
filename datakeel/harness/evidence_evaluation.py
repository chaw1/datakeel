# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Evaluate executed ObjectSets against independent generator gold and real extraction facts."""

import hashlib
from pathlib import Path
from time import perf_counter
from typing import Literal

from datakeel.core.errors import ValidationError
from datakeel.core.evidence_eval import EvidenceEvalReport, EvidenceQuestionResult
from datakeel.core.evidence_execution import EvidenceRunReport
from datakeel.core.evidence_models import Assertion
from datakeel.core.models import AssetRef
from datakeel.harness.evidence_metrics import (
    gold_pairs,
    gold_subset,
    macro_metrics,
    observed_pairs,
    presence_counts,
    retrieval_metrics,
    thresholds_met,
)
from datakeel.harness.evidence_questions import EvidenceQuestionSuite, load_evidence_questions
from datakeel.ontology.models import FrozenManifest
from datakeel.sample_evidence.models import SampleGold
from datakeel.storage.database import Database
from datakeel.storage.evidence_evaluations import benchmark_selections
from datakeel.storage.evidence_import import source_manifest
from datakeel.storage.evidence_runs import extraction_report
from datakeel.storage.evidence_store import list_assertions
from datakeel.storage.task_queries import query_task


def _questions(
    db: Database, dataset_id: str, version: str, gold: SampleGold, suite: EvidenceQuestionSuite
) -> tuple[EvidenceQuestionResult, ...]:
    queries = tuple(
        query.model_copy(update={"dataset_id": dataset_id, "version_ids": [version]})
        for question in suite.questions
        for query in (question.baseline, question.with_evidence)
    )
    selections = benchmark_selections(db, queries)
    return tuple(
        EvidenceQuestionResult(
            id=question.id,
            description=question.description,
            baseline_description=question.baseline_description,
            kind=question.target.kind,
            baseline=retrieval_metrics(
                _paths(selections[index * 2]), gold_subset(gold, question.target)
            ),
            with_evidence=retrieval_metrics(
                _paths(selections[index * 2 + 1]), gold_subset(gold, question.target)
            ),
        )
        for index, question in enumerate(suite.questions)
    )


def _paths(manifest: FrozenManifest) -> set[str]:
    if manifest.truncated:
        msg = "Benchmark query was truncated; metrics require the complete selection"
        raise ValidationError(msg)
    return {str(item.properties["filename"]) for item in manifest.objects}


def _source_assertions(db: Database, version: str, paths: dict[str, str]) -> tuple[Assertion, ...]:
    return tuple(
        item
        for item in list_assertions(db)
        if item.subject.version == version
        and item.subject.asset_id in paths
        and item.status in {"candidate", "accepted"}
        and (
            not isinstance(item.object, AssetRef)
            or (item.object.version == version and item.object.asset_id in paths)
        )
    )


def _load_gold(path: Path, paths: dict[str, str]) -> tuple[SampleGold, str]:
    content = path.read_bytes()
    gold = SampleGold.model_validate_json(content)
    if (
        set(paths.values()) != {sample.image for sample in gold.samples}
        or len(paths) != gold.sample_count
        or len(gold.samples) != gold.sample_count
    ):
        msg = "Gold sample paths and count must match the source manifest"
        raise ValidationError(msg)
    return gold, hashlib.sha256(content).hexdigest()


def _checked_extraction(
    db: Database, dataset_id: str, task_id: str, version: str
) -> EvidenceRunReport:
    task = query_task(db, task_id)
    report = extraction_report(db, task_id)
    if (
        task.dataset_id != dataset_id
        or task.state != "COMPLETED"
        or task.input_version_id not in (None, version)
        or not report.inputs
    ):
        msg = (
            "Benchmark extraction must be a completed evidence task for the source dataset/version"
        )
        raise ValidationError(msg)
    return report


def evaluate_evidence_dataset(
    db: Database,
    dataset_id: str,
    gold_path: Path,
    task_id: str,
    questions_path: Path | None = None,
    *,
    extraction_scope: Literal["fresh", "existing"] = "existing",
) -> EvidenceEvalReport:
    """Measure one existing source dataset without giving gold to any extractor or query."""
    started = perf_counter()
    suite, suite_digest = load_evidence_questions(questions_path)
    version, files = source_manifest(db, dataset_id)
    paths = {file.id: file.filename for file in files}
    gold, gold_digest = _load_gold(gold_path, paths)
    extraction = _checked_extraction(db, dataset_id, task_id, version)
    results = _questions(db, dataset_id, version, gold, suite)
    assertions = _source_assertions(db, version, paths)
    baseline = macro_metrics([result.baseline for result in results])
    evidence = macro_metrics([result.with_evidence for result in results])
    pairs = retrieval_metrics(observed_pairs(assertions, paths, gold), gold_pairs(gold))
    return EvidenceEvalReport(
        suite_digest=suite_digest,
        gold_digest=gold_digest,
        dataset_id=dataset_id,
        source_version=version,
        sample_count=len(files),
        questions=results,
        baseline_macro=baseline,
        with_evidence_macro=evidence,
        near_duplicate_pairs=pairs,
        val_to_train_pairs=retrieval_metrics(
            observed_pairs(assertions, paths, gold, cross_split=True),
            gold_pairs(gold, cross_split=True),
        ),
        presence_counts=presence_counts(assertions),
        extraction=extraction,
        extraction_scope=extraction_scope,
        evaluation_seconds=perf_counter() - started,
        thresholds=suite.thresholds,
        threshold_met=thresholds_met(baseline, evidence, pairs, suite.thresholds),
    )
