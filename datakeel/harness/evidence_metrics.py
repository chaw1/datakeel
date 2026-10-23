# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Compute independent gold subsets and direct-pair retrieval metrics without query leakage."""

from collections.abc import Collection, Hashable

from datakeel.core.evidence_eval import (
    EvidenceThresholds,
    GoldTarget,
    MacroMetrics,
    PresenceCounts,
    RetrievalMetrics,
)
from datakeel.core.evidence_models import Assertion, EvidenceValue
from datakeel.core.models import AssetRef
from datakeel.sample_evidence.models import GoldSample, SampleGold


def _pair(left: str, right: str) -> tuple[str, str]:
    return (left, right) if left < right else (right, left)


def retrieval_metrics[T: Hashable](
    selected: Collection[T], expected: Collection[T]
) -> RetrievalMetrics:
    """Measure set membership, counting missed gold even when prediction is empty."""
    predicted, gold = set(selected), set(expected)
    correct = len(predicted & gold)
    return RetrievalMetrics(
        selected=len(predicted),
        expected=len(gold),
        true_positive=correct,
        false_positive=len(predicted - gold),
        false_negative=len(gold - predicted),
        precision=correct / len(predicted) if predicted else 0,
        recall=correct / len(gold) if gold else 1,
    )


def macro_metrics(values: Collection[RetrievalMetrics]) -> MacroMetrics:
    """Compute an unweighted average over every question, not pooled micro counts."""
    return MacroMetrics(
        precision=sum(value.precision for value in values) / len(values) if values else 0,
        recall=sum(value.recall for value in values) / len(values) if values else 0,
    )


def thresholds_met(
    baseline: MacroMetrics,
    evidence: MacroMetrics,
    pairs: RetrievalMetrics,
    thresholds: EvidenceThresholds,
) -> bool:
    """Report comparison targets truthfully; callers must not turn this into command failure."""
    return (
        evidence.recall >= baseline.recall + thresholds.recall_gain
        and evidence.precision >= baseline.precision - thresholds.allowed_precision_drop
        and pairs.precision >= thresholds.pair_precision
        and pairs.recall >= thresholds.pair_recall
    )


def gold_pairs(gold: SampleGold, *, cross_split: bool = False) -> set[tuple[str, str]]:
    """Use only injected direct pairs, never a transitive closure or measured algorithm output."""
    splits = {sample.image: sample.split for sample in gold.samples}
    return {
        _pair(pair.left, pair.right)
        for pair in gold.near_duplicate_pairs
        if not cross_split or splits[pair.left] != splits[pair.right]
    }


def _sample_matches(sample: GoldSample, target: GoldTarget) -> bool:
    return (
        (target.split is None or sample.split == target.split)
        and (target.concept is None or target.concept in sample.concepts)
        and (target.scene is None or sample.scenes.get(target.scene) == "present")
    )


def gold_subset(gold: SampleGold, target: GoldTarget) -> set[str]:
    """Derive a question denominator exclusively from generator-authored ground truth."""
    splits = {sample.image: sample.split for sample in gold.samples}
    near = {
        source
        for pair in gold.near_duplicate_pairs
        for source, peer in ((pair.left, pair.right), (pair.right, pair.left))
        if target.peer_split is None or splits[peer] == target.peer_split
    }
    return {
        sample.image
        for sample in gold.samples
        if _sample_matches(sample, target)
        and (
            (target.kind == "near_duplicate" and sample.image in near)
            or (
                target.kind == "conflict"
                and (
                    target.concept in sample.label_gaps
                    if target.concept
                    else bool(sample.label_gaps)
                )
            )
            or (target.kind == "corrupt" and sample.corrupt)
            or (target.kind == "missing_annotation" and sample.missing_annotation)
        )
    }


def observed_pairs(
    assertions: Collection[Assertion],
    paths: dict[str, str],
    gold: SampleGold,
    *,
    cross_split: bool = False,
) -> set[tuple[str, str]]:
    """Map directly observed canonical relationships into gold-relative source paths."""
    splits = {sample.image: sample.split for sample in gold.samples}
    return {
        _pair(paths[item.subject.asset_id], paths[item.object.asset_id])
        for item in assertions
        if item.predicate == "near_duplicate_of"
        and isinstance(item.object, AssetRef)
        and item.subject.asset_id in paths
        and item.object.asset_id in paths
        and (
            not cross_split
            or splits[paths[item.subject.asset_id]] != splits[paths[item.object.asset_id]]
        )
    }


def presence_counts(assertions: Collection[Assertion]) -> PresenceCounts:
    """Count literal presence values from the evaluated source version's active assertions."""
    values = [item.object.value for item in assertions if isinstance(item.object, EvidenceValue)]
    return PresenceCounts(
        present=values.count("present"),
        absent=values.count("absent"),
        unknown=values.count("unknown"),
    )
