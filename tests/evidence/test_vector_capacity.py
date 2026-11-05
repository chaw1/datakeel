# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Capacity bounds count complete comparisons of eligible vectors only."""

from pathlib import Path

import pytest
from sqlalchemy import func, select

from datakeel.actions.parameters import PipelineParams
from datakeel.core.models import AssetRef
from datakeel.core.vector_models import DuplicateParams, VectorError, vector_hash
from datakeel.core.vector_results import VectorPair, VectorSample
from datakeel.evidence.vector_duplicate import direct_pairs
from datakeel.pipeline.models import Pipeline
from datakeel.storage.database import Database
from datakeel.storage.evidence_store import list_assertions
from datakeel.storage.vector_rows import VectorCacheRow
from tests.evidence.vector_helpers import (
    vector_dataset,
    vector_pipeline,
    vector_prepare,
    vector_run,
)


def _limited_pipeline(limit: int) -> Pipeline:
    pipeline = vector_pipeline()
    duplicate = pipeline.nodes[1].model_copy(
        update={"params": {"threshold": 0.0, "max_candidate_pairs": limit}}
    )
    return pipeline.model_copy(update={"nodes": [pipeline.nodes[0], duplicate]})


def test_direct_pairs_failed_samples_do_not_consume_comparison_budget() -> None:
    """A failed input has no vector and cannot contribute either comparison endpoint."""
    samples = tuple(
        VectorSample(
            subject=AssetRef(asset_type="file", asset_id=str(index), version="v1"),
            content_revision=vector_hash(str(index)),
            embedding_key=vector_hash([index]),
            vector=() if index == 2 else (1.0, 0.0),
            failure="missing_input" if index == 2 else None,
        )
        for index in range(3)
    )
    try:
        result = direct_pairs(samples, DuplicateParams(max_candidate_pairs=1))
    except VectorError:
        result = ()
    assert len(result) == 1


@pytest.mark.parametrize("invalid", [b"\xff", b""], ids=["invalid-utf8", "empty"])
def test_prepare_and_worker_invalid_input_at_exact_pair_limit_are_partial(
    db: Database, tmp_path: Path, invalid: bytes
) -> None:
    """Prepare, approval, worker and hot reuse retain two eligible inputs and one pair."""
    dataset = vector_dataset(db, tmp_path / "inputs", (b"one", invalid, b"three"))
    pipeline = _limited_pipeline(1)
    try:
        plan = vector_prepare(db, dataset, pipeline)
    except VectorError:
        plan = None
    assert plan is not None
    prepared = PipelineParams.model_validate(plan.canonical_params).vector_prepared
    assert prepared is not None
    assert prepared.worst_requests == 2
    for _ in range(2):
        task = vector_run(db, dataset, pipeline)
        assert task.state == "COMPLETED", task.error
        assert task.partial
        assert task.vector is not None
        assert task.vector.status == "partial_success"
        assert all(
            node.counts.eligible == 2 and node.counts.failed == 1 for node in task.vector.nodes
        )
    assert len(list_assertions(db)) == 1


@pytest.mark.parametrize("invalid", [False, True])
def test_prepare_rejects_complete_eligible_comparisons_over_limit(
    db: Database, tmp_path: Path, *, invalid: bool
) -> None:
    """Three valid inputs still fail before any approval or truncated publication."""
    contents = (b"one", b"two", b"three") + ((b"\xff",) if invalid else ())
    dataset = vector_dataset(db, tmp_path / "inputs", contents)
    with pytest.raises(VectorError, match="vector_capacity_exceeded"):
        vector_prepare(db, dataset, _limited_pipeline(1))
    assert list_assertions(db) == []


def test_runtime_capacity_failure_discards_all_pending_products(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A runtime comparison bound fails the whole task after embedding, with no truncated result."""
    dataset = vector_dataset(db, tmp_path / "inputs")

    def constrained(
        samples: tuple[VectorSample, ...], params: DuplicateParams
    ) -> tuple[VectorPair, ...]:
        return direct_pairs(samples, params.model_copy(update={"max_candidate_pairs": 1}))

    monkeypatch.setattr("datakeel.evidence.vector_execution.direct_pairs", constrained)
    task = vector_run(db, dataset)
    assert task.state == "FAILED"
    assert task.vector is not None
    assert task.vector.status == "failed"
    assert task.vector.reason == "vector_capacity_exceeded"
    assert len(task.vector.attempts) == 3
    assert list_assertions(db) == []
    with db.session() as session:
        assert session.scalar(select(func.count()).select_from(VectorCacheRow)) == 0
