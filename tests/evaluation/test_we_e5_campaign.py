# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Real controlled fake-worker runs and falsified-evidence rejection, without model or network."""

import json
from pathlib import Path

import pytest

from scripts.we_e5.campaign import run_campaign, validate_phases
from scripts.we_e5.campaign_models import Campaign, Phase
from scripts.we_e5.models import Workload


@pytest.fixture(scope="module")
def campaign(tmp_path_factory: pytest.TempPathFactory) -> Campaign:
    """Freeze one small complete run, retaining the same real worker behavior as the CLI."""
    return run_campaign(
        tmp_path_factory.mktemp("we-e5-campaign"), Workload(assets=9, repetitions=1), ("pytest",)
    )


def _rejection(phases: tuple[Phase, ...], workload: Workload) -> str | None:
    try:
        validate_phases(phases, workload)
    except ValueError as error:
        return str(error)
    return None


def test_real_worker_cold_hot_incremental_counters_and_scope(campaign: Campaign) -> None:
    """Durable attempt identities, observed kernels, caches and explicit versions agree."""
    cold, hot, incremental = campaign.phases
    assert cold.dispatch_count == len(cold.attempted_asset_ids) == 11
    assert hot.dispatch_count == len(hot.attempted_asset_ids) == 0
    assert incremental.dispatch_count == 1
    assert incremental.attempted_asset_ids == ("target-00000",)
    assert cold.pair_comparisons == cold.cluster_comparisons == cold.outlier_comparisons == 36
    assert hot.pair_comparisons == hot.cluster_comparisons == hot.outlier_comparisons == 0
    assert cold.reference_comparisons == incremental.reference_comparisons == 18
    assert hot.reference_comparisons == 0
    assert cold.facts_hash == hot.facts_hash != incremental.facts_hash
    assert cold.source_version_id == hot.source_version_id != incremental.source_version_id
    assert len({p.task_id for p in campaign.phases}) == len(campaign.phases)
    assert len({p.run_id for p in campaign.phases}) == len(campaign.phases)
    assert all(p.wall_seconds > 0 and p.rss_bytes > 0 for p in campaign.phases)
    assert hot.fake_usage == 0
    assert all(p.fake_price == p.real_spend_cny == 0 for p in campaign.phases)
    assert len(cold.cache_after.globals) == len(hot.cache_after.globals) == 4
    assert all(
        n.vector and n.vector.cache_hits == n.vector.counts.input for n in hot.report.operators
    )
    assert len(incremental.cache_after.embeddings) == len(hot.cache_after.embeddings) + 1
    assert _rejection(campaign.phases, campaign.workload) is None


def test_hot_evidence_with_nonzero_calls_is_rejected(campaign: Campaign) -> None:
    """A hot timing cannot claim zero calls when the observed transport count is nonzero."""
    cold, hot, incremental = campaign.phases
    poisoned = hot.model_copy(update={"dispatch_count": 1})
    assert _rejection((cold, poisoned, incremental), campaign.workload) is not None


def test_incremental_evidence_wrong_peer_is_rejected(campaign: Campaign) -> None:
    """One call alone is insufficient: only the explicitly changed asset may be reembedded."""
    cold, hot, incremental = campaign.phases
    poisoned = incremental.model_copy(update={"attempted_asset_ids": ("target-00001",)})
    assert _rejection((cold, hot, poisoned), campaign.workload) is not None


def test_cold_evidence_with_existing_cache_is_rejected(campaign: Campaign) -> None:
    """A nonempty embedding cache independently prevents a warm-cache cold measurement."""
    cold, hot, incremental = campaign.phases
    before = cold.cache_before.model_copy(update={"embeddings": hot.cache_before.embeddings})
    poisoned = cold.model_copy(update={"cache_before": before})
    assert before.globals == ()
    assert _rejection((poisoned, hot, incremental), campaign.workload) is not None


def test_cold_evidence_with_existing_globals_is_rejected(campaign: Campaign) -> None:
    """A nonempty global cache independently prevents a warm-cache cold measurement."""
    cold, hot, incremental = campaign.phases
    before = cold.cache_before.model_copy(update={"globals": hot.cache_before.globals})
    poisoned = cold.model_copy(update={"cache_before": before})
    assert before.embeddings == ()
    assert _rejection((poisoned, hot, incremental), campaign.workload) is not None


def test_insufficient_population_matches_worker_published_noise(tmp_path: Path) -> None:
    """Raw DBSCAN labels stay available without becoming published outliers on either backend."""
    report = run_campaign(
        tmp_path / "insufficient", Workload(assets=9, repetitions=1, min_samples=10), ("pytest",)
    )
    comparison = report.comparisons[1]
    assert comparison.recorded_worker is not None
    assert comparison.recorded_worker.noise == ()
    assert comparison.f64.labels == comparison.faiss.labels == (-1,) * 9
    assert comparison.f64.noise == comparison.faiss.noise == ()
    assert comparison.worker_f64_differences == comparison.worker_faiss_differences == ()
    for metrics in (comparison.f64_quality, comparison.faiss_quality):
        assert metrics.noise != "not_available"
        assert (metrics.noise.predicted, metrics.noise.expected, metrics.noise.f1) == (0, 0, 1)


def test_identical_command_reproduces_facts_not_timing(tmp_path: Path) -> None:
    """Two complete campaigns have the same frozen input and measured facts, with fresh runs."""
    workload = Workload(assets=9, repetitions=2)
    a = run_campaign(tmp_path / "a", workload, ("same-command",))
    b = run_campaign(tmp_path / "b", workload, ("same-command",))
    assert a.workload_sha256 == b.workload_sha256
    assert a.reproducible_facts_hash == b.reproducible_facts_hash
    assert len(a.phases) == 6
    assert a.phases[0].task_id != b.phases[0].task_id
    assert a.semantic_quality == a.cloud_latency == "not_tested"
    assert a.real_spend_cny == 0
    assert len(a.summaries) == 3
    assert a.summaries[0].wall_seconds == (a.phases[0].wall_seconds, a.phases[3].wall_seconds)
    assert all((tmp_path / "a" / f"raw-{i:02d}.json").exists() for i in range(2))
    assert (
        json.loads((tmp_path / "a/workload.json").read_text())["workload"]["seed"] == workload.seed
    )
