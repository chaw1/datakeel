# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Exact configured capacity and all-or-nothing pending publication over generated data."""

from pathlib import Path

import pytest
from sqlalchemy import func, select

from datakeel.core.errors import ValidationError
from datakeel.core.evidence_execution import EvidenceExecutionContext
from datakeel.core.models import AssetRef
from datakeel.core.vector_models import ClusterParams, VectorError
from datakeel.dataset_store.datasets import materialize_files
from datakeel.evidence.vector_execution import VectorExecution
from datakeel.evidence.vector_parameters import CoverageParams
from datakeel.evidence.vector_sets import cluster_findings, coverage_findings, dbscan
from datakeel.ontology.models import ObjectSet
from datakeel.persistence.task_queue import DatabaseQueue
from datakeel.pipeline import run_pipeline
from datakeel.pipeline.models import Node
from datakeel.pipeline.sharding import validate_shards
from datakeel.storage.database import Database
from datakeel.storage.evidence_projection import projection_hash
from datakeel.storage.evidence_store import list_assertions
from datakeel.storage.vector_authorization import vector_permit
from datakeel.storage.vector_rows import VectorCacheRow
from tests.evidence.test_vector_set_execution import set_pipeline
from tests.evidence.test_vector_sets import sample, scope
from tests.evidence.vector_helpers import (
    vector_dataset,
    vector_prepare,
    vector_run,
    vector_schedule,
)


def test_set_sample_limit_5000_and_5001_rejection() -> None:
    """Failed samples still count against the complete sample cap, without needless comparisons."""
    base = sample("source", failed=True)
    points = tuple(
        base.model_copy(
            update={"subject": AssetRef(asset_type="file", asset_id=str(i), version="v1")}
        )
        for i in range(5000)
    )
    assert dbscan(points, ClusterParams())[1] == ()
    refused = False
    try:
        dbscan((*points, base), ClusterParams())
    except VectorError:
        refused = True
    assert refused


def test_set_pair_limit_249571_accepts_250278_refuses() -> None:
    """Complete direct pairs cross the default bound between 707 and 708 eligible points."""
    points = tuple(sample(str(i)) for i in range(707))
    assert len(cluster_findings(points, ClusterParams(eps=0.0, min_samples=2))) == 707
    refused = False
    try:
        cluster_findings((*points, sample("last")), ClusterParams())
    except VectorError:
        refused = True
    assert refused


def test_gap_exact_250000_comparisons_and_one_over_refuses() -> None:
    """The independent reference cap admits exactly 500 times 500 with no truncation."""
    targets = tuple(sample(f"t-{i}") for i in range(500))
    refs = tuple(sample(f"r-{i}") for i in range(500))
    params = CoverageParams(reference=ObjectSet(), threshold=-1.0)
    assert coverage_findings((*targets, *refs), scope(targets, refs), params) == ()
    extra = sample("extra")
    refused = False
    try:
        coverage_findings((*targets, extra, *refs), scope((*targets, extra), refs), params)
    except VectorError:
        refused = True
    assert refused


@pytest.mark.parametrize(
    "operator", ["evidence.semantic_cluster", "evidence.semantic_outlier", "evidence.coverage_gap"]
)
def test_all_set_operators_refuse_multiple_shards(operator: str) -> None:
    """Direct queue and preparation share the set-scoped single-shard guard."""
    params = {"reference": {}} if operator.endswith("gap") else {}
    pipeline = set_pipeline(operator, params)
    with pytest.raises(ValidationError, match="one shard"):
        validate_shards(pipeline, 2)


def test_successful_set_then_late_failure_discards_pending_retains_history_and_charges(
    db: Database, tmp_path: Path
) -> None:
    """A successful cluster pending result cannot leak when the last set node fails."""
    dataset = vector_dataset(db, tmp_path / "old", (b"same", b"same", b"other"))
    pipeline = set_pipeline("evidence.semantic_cluster", {"eps": 0.0, "min_samples": 2})
    assert vector_run(db, dataset, pipeline).state == "COMPLETED"
    history = list_assertions(db)
    old_hash = projection_hash(db)
    with db.session() as session:
        old_count = session.scalar(select(func.count()).select_from(VectorCacheRow))
    new_dataset = vector_dataset(db, tmp_path / "new", (b"new", b"new", b"unique"))
    last = Node(
        id="late",
        operator="evidence.coverage_gap",
        inputs={"files": "set.files"},
        params={
            "reference": {"dataset_id": dataset, "filters": [{"field": "id", "value": "none"}]}
        },
    )
    failing = pipeline.model_copy(
        update={"nodes": [*pipeline.nodes, last], "outputs": ["late.files"]}
    )
    task = vector_run(db, new_dataset, failing)
    assert task.state == "FAILED"
    assert task.vector
    assert task.vector.reason == "vector_reference_empty"
    assert task.vector.attempts
    assert list_assertions(db) == history
    assert projection_hash(db) == old_hash
    with db.session() as session:
        assert session.scalar(select(func.count()).select_from(VectorCacheRow)) == old_count


def test_set_error_completion_discards_successful_pending(db: Database, tmp_path: Path) -> None:
    """Terminal failure discards every successful pending set product."""
    dataset = vector_dataset(db, tmp_path / "inputs", (b"same", b"same", b"other"))
    pipeline = set_pipeline("evidence.semantic_cluster", {"eps": 0.0, "min_samples": 2})
    vector_schedule(db, vector_prepare(db, dataset, pipeline))
    queue = DatabaseQueue(db)
    lease = queue.claim()
    assert lease
    permit = vector_permit(db, lease.task_id, lease.shard_id, lease.owner)
    executor = VectorExecution(
        db,
        EvidenceExecutionContext(
            task_id=lease.task_id,
            shard_id=lease.shard_id,
            version_id=lease.input_version_id or "missing",
        ),
        permit,
    )
    outputs = run_pipeline(
        materialize_files(lease.inputs),
        tmp_path / "out",
        lease.pipeline,
        operator_executor=executor.execute_node,
    )
    assert len(executor.pending) == 2
    assert executor.pending[-1].bundle.assertions
    assert queue.finish(
        lease, outputs, [], error="vector_late_fixture_failure", evidence=tuple(executor.pending)
    )
    assert list_assertions(db) == []
    with db.session() as session:
        assert session.scalar(select(func.count()).select_from(VectorCacheRow)) == 0
