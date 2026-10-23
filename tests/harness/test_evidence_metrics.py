# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Independent denominators, direct pairs, and honest threshold calculations."""

from pathlib import Path

import pytest

from datakeel.core.evidence_eval import EvidenceThresholds, GoldTarget, MacroMetrics
from datakeel.core.evidence_models import Assertion, EvidenceAnchor, ExtractorRef
from datakeel.core.models import AssetRef
from datakeel.harness.evidence_metrics import (
    gold_pairs,
    gold_subset,
    macro_metrics,
    observed_pairs,
    retrieval_metrics,
    thresholds_met,
)
from datakeel.sample_evidence import generate_samples


def test_retrieval_metrics_when_sets_overlap_counts_all_false_positives_and_misses() -> None:
    """Measure set membership rather than selected-row count or a shared denominator."""
    metrics = retrieval_metrics(["a", "a", "wrong"], ["a", "b", "c"])
    assert (metrics.selected, metrics.expected, metrics.true_positive) == (2, 3, 1)
    assert (metrics.false_positive, metrics.false_negative) == (1, 2)
    assert metrics.precision == 0.5
    assert metrics.recall == pytest.approx(1 / 3)
    assert retrieval_metrics([], ["a"]).precision == 0
    assert retrieval_metrics([], ["a"]).recall == 0
    assert retrieval_metrics([], []).recall == 1


def test_macro_and_thresholds_when_targets_unmet_report_false_without_exception() -> None:
    """Keep per-question averaging and all published comparison conditions effective."""
    good = retrieval_metrics(["a"], ["a"])
    poor = retrieval_metrics([], ["a", "b", "c"])
    assert macro_metrics([good, poor]) == MacroMetrics(precision=0.5, recall=0.5)
    assert macro_metrics([]) == MacroMetrics(precision=0, recall=0)
    limits = EvidenceThresholds()
    low, high = MacroMetrics(precision=0.5, recall=0.5), MacroMetrics(precision=1, recall=1)
    assert thresholds_met(low, high, good, limits)
    assert not thresholds_met(high, high, good, limits)
    assert not thresholds_met(high, low, good, limits)
    assert not thresholds_met(low, high, poor, limits)


def test_gold_when_conflict_concept_differs_does_not_borrow_another_concepts_gap(
    tmp_path: Path,
) -> None:
    """A caption containing car does not turn a missing person label into a car-label gap."""
    gold = generate_samples(tmp_path, samples=100)
    assert gold_subset(gold, GoldTarget(kind="conflict"))
    assert gold_subset(gold, GoldTarget(kind="conflict", concept="person"))
    assert gold_subset(gold, GoldTarget(kind="conflict", concept="car")) == set()
    assert len(gold_subset(gold, GoldTarget(kind="corrupt"))) == 1
    assert len(gold_subset(gold, GoldTarget(kind="missing_annotation"))) == 3


def test_pair_metrics_when_nontransitive_chain_present_never_expand_endpoints(
    tmp_path: Path,
) -> None:
    """Keep gold and observed pairs direct and report the cross-split gold denominator."""
    gold = generate_samples(tmp_path, samples=100)
    chain = gold.non_transitive_chains[0]
    assert (chain.a, chain.c) not in gold_pairs(gold)
    assert len(gold_pairs(gold)) == 7
    assert len(gold_pairs(gold, cross_split=True)) == 6
    left = AssetRef(asset_type="file", asset_id="a", version="source")
    right = AssetRef(asset_type="file", asset_id="b", version="source")
    assertion = Assertion(
        subject=left,
        object=right,
        predicate="near_duplicate_of",
        distance=6,
        anchors=(EvidenceAnchor(asset_ref=left, content_revision="0" * 64),),
        extractor=ExtractorRef(id="evidence.near_duplicate", version="1"),
        producer_event_id="event",
        run_id="run",
    )
    assert observed_pairs([assertion], {"a": chain.b, "b": chain.a}, gold) == {(chain.a, chain.b)}
    assert (
        observed_pairs([assertion], {"a": chain.b, "b": chain.a}, gold, cross_split=True) == set()
    )
    assert observed_pairs([assertion], {"a": chain.c, "b": chain.b}, gold, cross_split=True) == {
        (chain.b, chain.c)
    }
    assert observed_pairs([assertion], {}, gold) == set()
