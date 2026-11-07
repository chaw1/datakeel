# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Typed campaign records retain raw repetitions, cache identities and durable run IDs."""

from typing import Literal

from datakeel.core.evidence_execution import EvidenceRunReport
from datakeel.core.models import BoundaryModel
from datakeel.core.vector_models import VectorPrepared
from datakeel.core.vector_results import VectorSample
from scripts.we_e5.models import RecordedFacts, Workload
from scripts.we_e5.report import NumericReport


class Fixture(BoundaryModel):
    """Reference only the locally generated source and reference snapshots."""

    dataset_id: str
    version_id: str
    reference_dataset_id: str
    target_ids: tuple[str, ...]
    reference_ids: tuple[str, ...]


class CacheSnapshot(BoundaryModel):
    """Expose typed cache keys and sample ownership without leaking ORM rows."""

    embeddings: tuple[tuple[str, tuple[str, ...]], ...]
    globals: tuple[str, ...]


class Phase(BoundaryModel):
    """One actual prepared, approved and worker-completed end-to-end operation."""

    name: Literal["cold", "hot", "incremental"]
    repetition: int
    dataset_id: str
    source_version_id: str
    plan_id: str
    plan_digest: str
    task_id: str
    run_id: str
    wall_seconds: float
    rss_raw: int
    rss_bytes: int
    rss_source_unit: str
    cache_before: CacheSnapshot
    cache_after: CacheSnapshot
    attempted_asset_ids: tuple[str, ...]
    dispatch_count: int
    pair_comparisons: int
    cluster_comparisons: int
    outlier_comparisons: int
    reference_comparisons: int
    report: EvidenceRunReport
    facts_hash: str
    samples: tuple[VectorSample, ...]
    recorded: RecordedFacts
    fake_usage: int
    prepared: VectorPrepared
    fake_price: Literal[0] = 0
    real_spend_cny: Literal[0] = 0


class Summary(BoundaryModel):
    """Timing samples remain alongside min/median/max, without performance assertions."""

    phase: str
    wall_seconds: tuple[float, ...]
    rss_bytes: tuple[int, ...]
    wall_min: float
    wall_median: float
    wall_max: float
    rss_max: int


class Campaign(BoundaryModel):
    """Freeze fake-worker scope, limitations and measured phases separately from quality."""

    workload: Workload
    workload_sha256: str
    environment: dict[str, str | int]
    command: tuple[str, ...]
    phases: tuple[Phase, ...]
    summaries: tuple[Summary, ...]
    comparisons: tuple[NumericReport, ...]
    reproducible_facts_hash: str
    semantic_quality: Literal["not_tested"] = "not_tested"
    cloud_latency: Literal["not_tested"] = "not_tested"
    real_spend_cny: Literal[0] = 0
    rss_limitation: str = "process_lifetime_peak_not_precise_phase_increment"
    time_scope: str = "local_fake_worker_prepare_approve_execute_worker_readback"
    gold_scope: str = "synthetic_contract_only_not_encoder_quality"
