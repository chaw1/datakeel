# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Bind restored private graph inputs to the same authorized worker lease and run."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from datakeel.actions.models import ExecuteRequest
from datakeel.actions.service import execute_plan
from datakeel.core.errors import ConflictError, ValidationError
from datakeel.core.kg_execution import KGLeaseFence
from datakeel.storage.kg_inputs import restore_inputs
from datakeel.storage.kg_store import get_job
from datakeel.worker.queue import DatabaseQueue
from tests.kg.integration_helpers import prepare_graph, text_dataset

if TYPE_CHECKING:
    from pathlib import Path

    from datakeel.storage.database import Database


@pytest.mark.parametrize("invalid", ["cancelled_lease", "missing_run"])
def test_verified_sources_cannot_be_persisted_without_the_owning_run_and_lease(
    db: Database, tmp_path: Path, invalid: str
) -> None:
    """Even matching bytes cannot cross a cancelled or mismatched publication boundary."""
    dataset = text_dataset(db, tmp_path, ("Acme uses Widget.",))
    plan = prepare_graph(db, dataset)
    execute_plan(db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest))
    queue = DatabaseQueue(db)
    lease = queue.claim()
    assert lease is not None
    assert lease.kg_run_id is not None
    job = get_job(db, lease.kg_run_id)
    fence = KGLeaseFence(task_id=lease.task_id, shard_id=lease.shard_id, owner=lease.owner)
    if invalid == "cancelled_lease":
        assert queue.cancel(lease.task_id)
        with pytest.raises(ConflictError, match="lease was lost"):
            restore_inputs(db, job, fence)
    else:
        altered = job.model_copy(update={"run": job.run.model_copy(update={"id": "missing"})})
        with pytest.raises(ValidationError, match="does not belong"):
            restore_inputs(db, altered, fence)
    assert get_job(db, job.run.id).documents == ()
