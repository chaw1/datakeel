# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Failures, continuation, budget stops and lease fences through the actual graph worker."""

from __future__ import annotations

from typing import TYPE_CHECKING, Never

import pytest
from sqlalchemy import func, select

from datakeel.actions.models import ExecuteRequest
from datakeel.actions.service import execute_plan, prepare_action
from datakeel.core.errors import ValidationError
from datakeel.core.kg_execution import KGCompletion, KGLeaseFence
from datakeel.core.kg_product import ProductExtraction
from datakeel.core.models import JsonDocument
from datakeel.kg.cache import build_cache_key, extraction_identity
from datakeel.storage.database import VersionRow
from datakeel.storage.evidence_store import list_assertions
from datakeel.storage.harness_service import list_traces
from datakeel.storage.kg_store import cache_block, cached_block, get_job, list_runs, start_run
from datakeel.worker.queue import DatabaseQueue
from datakeel.worker.runner import execute
from tests.kg.integration_helpers import (
    execute_graph,
    install_adapter,
    pair_result,
    prepare_graph,
    text_dataset,
)

if TYPE_CHECKING:
    from pathlib import Path

    from datakeel.storage.database import Database


@pytest.mark.parametrize(
    "reason", ["parse_failure", "provider_error", "replay_missing", "truncated"]
)
def test_failed_blocks_retry_without_repeating_successful_blocks(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, reason: str
) -> None:
    """Failed attempts are visible and settled, while only complete output becomes reusable."""
    dataset = text_dataset(db, tmp_path, ("Acme uses Widget. A.", "Acme uses Widget. B."))
    failure = (
        pair_result().model_copy(update={"finish_reason": "length"})
        if reason == "truncated"
        else reason
    )
    adapter = install_adapter(monkeypatch, (pair_result(), failure, pair_result()))
    first = execute_graph(db, prepare_graph(db, dataset))
    assert first.status == "partial"
    assert (first.report.extracted, first.report.failed, first.report.model_calls) == (1, 1, 2)
    assert first.report.failures[0].reason == reason
    assert first.report.partial_documents == (dataset.files[1].id,)
    assert len(list_traces(db, first.id)) == 2
    second = execute_graph(db, prepare_graph(db, dataset))
    assert second.status == "completed"
    assert (second.report.cached, second.report.extracted, second.report.model_calls) == (1, 1, 1)
    assert adapter.calls == 3
    assert all(item.status == "candidate" for item in list_assertions(db))
    with db.session() as session:
        assert session.scalar(select(func.count()).select_from(VersionRow)) == 1


def test_zero_budget_retains_cache_and_retries_only_unexecuted_documents(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A zero-budget rerun still reads prior successes and visibly defers missing blocks."""
    dataset = text_dataset(db, tmp_path, ("Acme uses Widget. A.", "Acme uses Widget. B."))
    adapter = install_adapter(monkeypatch, (pair_result(), pair_result()))
    execute_graph(db, prepare_graph(db, dataset, file_ids=(dataset.files[0].id,)))
    plan = prepare_action(
        db,
        "run_kg_extraction",
        JsonDocument(
            root={
                "dataset_id": dataset.dataset_id,
                "version_id": dataset.version_id,
                "profile_id": "fake",
                "budget_tokens": 0,
            }
        ),
    )
    stopped = execute_graph(db, plan)
    assert stopped.status == "budget_exceeded"
    assert (stopped.report.cached, stopped.report.unexecuted, stopped.report.model_calls) == (
        1,
        1,
        0,
    )
    assert stopped.report.failures[0].attempted is False
    resumed = execute_graph(db, prepare_graph(db, dataset))
    assert resumed.status == "completed"
    assert (resumed.report.cached, resumed.report.extracted) == (1, 1)
    assert adapter.calls == 2


def test_cancelled_lease_cannot_publish_cache_or_graph(db: Database, tmp_path: Path) -> None:
    """Cancellation fences late model output before cache, assertions and run updates."""
    dataset = text_dataset(db, tmp_path, ("Acme uses Widget.",))
    plan = prepare_graph(db, dataset)
    execute_plan(db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest))
    queue = DatabaseQueue(db)
    lease = queue.claim()
    assert lease is not None
    assert lease.kg_run_id is not None
    job = get_job(db, lease.kg_run_id)
    prepared = job.prepared
    fence = KGLeaseFence(task_id=lease.task_id, shard_id=lease.shard_id, owner=lease.owner)
    key = build_cache_key(
        prepared.documents[0].blocks[0],
        prepared.schema_definition,
        prepared.profile,
        extraction_identity(prepared.schema_definition, prepared.profile),
    )
    assert queue.cancel(lease.task_id)
    assert not start_run(db, job.run.id, fence)
    assert not cache_block(db, fence, key, pair_result())
    assert cached_block(db, key) is None
    completion = KGCompletion(run=job.run, products=ProductExtraction())
    assert not queue.finish(lease, [], [], evidence=completion)
    assert not execute(queue, lease)
    assert list_assertions(db) == []
    failed = get_job(db, job.run.id).run
    assert failed.status == "failed"
    assert failed.report.unexecuted == 1
    with pytest.raises(ValidationError, match="Truncated"):
        cache_block(db, fence, key, pair_result().model_copy(update={"finish_reason": "length"}))


def test_adapter_construction_failure_is_terminal_and_has_no_model_call(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Missing optional providers cannot strand a running report or fabricate a trace."""

    def unavailable(*_args: object, **_kwargs: object) -> Never:
        msg = "Generated unavailable provider"
        raise ImportError(msg)

    dataset = text_dataset(db, tmp_path, ("Acme uses Widget.",))
    monkeypatch.setattr("datakeel.worker.kg_runner.create_extractor", unavailable)
    run = execute_graph(db, prepare_graph(db, dataset))
    assert run.status == "failed"
    assert run.report.error == "Graph extraction failed: ImportError"
    assert run.report.unexecuted == 1
    assert list_traces(db, run.id) == []
    assert len(list_runs(db, dataset.dataset_id, dataset.version_id, limit=1)) == 1
    with pytest.raises(ValidationError, match="limit"):
        list_runs(db, limit=0)
