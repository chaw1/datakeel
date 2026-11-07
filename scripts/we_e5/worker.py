# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Use the real controlled-action, approval, queue and worker path on an owned local store."""

import resource
import sys
from time import perf_counter
from typing import Literal

from datakeel.actions.models import ActionPlan, ActionRun, ApprovalDecision, ExecuteRequest
from datakeel.actions.service import approve_plan, execute_plan, prepare_action
from datakeel.core.evidence_execution import EvidenceRunReport
from datakeel.core.models import BoundaryModel, JsonDocument
from datakeel.core.vector_models import VectorPrepared, vector_hash
from datakeel.persistence.task_queries import query_task
from datakeel.pipeline.models import Node, Pipeline
from datakeel.storage.database import Database
from datakeel.storage.evidence_runs import extraction_report
from datakeel.worker.runner import run_worker
from scripts.we_e5.campaign_models import Fixture, Phase
from scripts.we_e5.models import Workload
from scripts.we_e5.probes import Counters, observed
from scripts.we_e5.store import attempted_assets, cache_snapshot, recorded_facts, recorded_samples


def pipeline(fixture: Fixture, workload: Workload) -> Pipeline:
    """Run all four evidence computations with explicit fake policy and one DAG worker."""
    nodes = [
        Node(
            id="embed",
            operator="evidence.vector_embed",
            inputs={"files": "$input.files"},
            params={"dimensions": workload.dimensions, "policy": {"nanos_per_token": 0}},
        )
    ]
    for name, operator, params in (
        ("pairs", "evidence.semantic_duplicate", {"threshold": workload.duplicate_threshold}),
        (
            "cluster",
            "evidence.semantic_cluster",
            {"eps": workload.eps, "min_samples": workload.min_samples},
        ),
        (
            "outlier",
            "evidence.semantic_outlier",
            {"eps": workload.eps, "min_samples": workload.min_samples},
        ),
        (
            "gap",
            "evidence.coverage_gap",
            {
                "threshold": workload.gap_threshold,
                "reference": {"dataset_id": fixture.reference_dataset_id},
            },
        ),
    ):
        nodes.append(
            Node(id=name, operator=operator, inputs={"files": "embed.files"}, params=params)
        )
    return Pipeline(nodes=nodes, outputs=["gap.files"], max_workers=workload.workers)


def rss_bytes(raw: int, platform: str) -> int:
    """Normalize ru_maxrss: bytes on Darwin, KiB on Linux; reject unqualified platforms."""
    if platform == "darwin":
        return raw
    if platform.startswith("linux"):
        return raw * 1024
    msg = "unqualified_rss_platform"
    raise ValueError(msg)


class Execution(BoundaryModel):
    """Carry completed local action and measured counters to evidence serialization."""

    plan: ActionPlan
    action: ActionRun
    report: EvidenceRunReport
    prepared: VectorPrepared
    elapsed: float
    measured: Counters


def _execute(db: Database, fixture: Fixture, workload: Workload) -> Execution:
    started = perf_counter()
    with observed() as measured:
        plan = prepare_action(
            db,
            "run_pipeline",
            JsonDocument.model_validate(
                {
                    "dataset_id": fixture.dataset_id,
                    "version_id": fixture.version_id,
                    "pipeline": pipeline(fixture, workload).model_dump(mode="json"),
                }
            ),
        )
        prepared = VectorPrepared.model_validate(plan.canonical_params["vector_prepared"])
        approve_plan(db, plan.id, ApprovalDecision(approve=True, plan_digest=plan.plan_digest))
        action = execute_plan(db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest))
        if action.task_id is None:
            msg = "controlled_action_did_not_schedule_worker"
            raise ValueError(msg)
        run_worker(db, once=True)
        task = query_task(db, action.task_id)
        report = extraction_report(db, task.id)
    elapsed = perf_counter() - started
    if (
        task.state != "COMPLETED"
        or task.partial
        or len(report.operators) != len(pipeline(fixture, workload).nodes)
    ):
        msg = f"fake_worker_incomplete: {task.state}: {task.error}"
        raise ValueError(msg)
    return Execution(
        plan=plan,
        action=action,
        report=report,
        prepared=prepared,
        elapsed=elapsed,
        measured=measured,
    )


def run_phase(
    db: Database,
    fixture: Fixture,
    workload: Workload,
    name: Literal["cold", "hot", "incremental"],
    repetition: int,
) -> Phase:
    """Measure monotonic wall time from prepare through completed persisted report readback."""
    before = cache_snapshot(db)
    execution = _execute(db, fixture, workload)
    plan, action, report = execution.plan, execution.action, execution.report
    prepared, measured = execution.prepared, execution.measured
    raw_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return Phase(
        name=name,
        repetition=repetition,
        dataset_id=fixture.dataset_id,
        source_version_id=fixture.version_id,
        plan_id=plan.id,
        plan_digest=plan.plan_digest,
        task_id=str(action.task_id),
        run_id=action.id,
        wall_seconds=execution.elapsed,
        rss_raw=raw_rss,
        rss_bytes=rss_bytes(raw_rss, sys.platform),
        rss_source_unit="bytes" if sys.platform == "darwin" else "KiB",
        cache_before=before,
        cache_after=cache_snapshot(db),
        attempted_asset_ids=attempted_assets(db, str(action.task_id)),
        dispatch_count=measured.dispatch,
        pair_comparisons=measured.pairs,
        cluster_comparisons=measured.cluster,
        outlier_comparisons=measured.outlier,
        reference_comparisons=measured.reference,
        report=report,
        facts_hash=vector_hash(
            sorted(
                (n.operator, n.vector.canonical_hash)
                for n in report.operators
                if n.vector is not None
            )
        ),
        samples=recorded_samples(db, str(action.task_id)),
        recorded=recorded_facts(db, str(action.task_id)),
        fake_usage=sum(n.vector.fake_usage for n in report.operators if n.vector is not None),
        prepared=prepared,
    )
