# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Global near-duplicate extraction cannot silently lose pairs across worker shards."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from datakeel.actions.service import prepare_action
from datakeel.core.errors import ValidationError
from datakeel.core.models import JsonDocument
from datakeel.pipeline.evidence import evidence_pipeline
from datakeel.pipeline.sharding import validate_shards
from datakeel.storage.action_operations import execute_business
from datakeel.storage.task_queue import DatabaseQueue
from tests.evidence.test_execution import seed_evidence

if TYPE_CHECKING:
    from pathlib import Path

    from datakeel.storage.database import Database


def test_global_near_duplicate_rejects_multiple_shards_at_every_submission_boundary(
    db: Database,
    tmp_path: Path,
) -> None:
    """Reject direct queue, controlled preparation, and execution-time multisharding."""
    dataset_id = seed_evidence(db, tmp_path / "samples")
    definition = evidence_pipeline()
    validate_shards(None, 8)
    validate_shards(definition, 1)
    with pytest.raises(ValidationError, match="exactly one shard"):
        DatabaseQueue(db).submit(dataset_id, "split", definition, shards=2)
    params = {"dataset_id": dataset_id, "pipeline": definition.model_dump(mode="json"), "shards": 2}
    with pytest.raises(ValidationError, match="exactly one shard"):
        prepare_action(db, "run_pipeline", JsonDocument.model_validate(params))
    params["shards"] = 1
    plan = prepare_action(db, "run_pipeline", JsonDocument.model_validate(params))
    altered = plan.model_copy(update={"canonical_params": {**plan.canonical_params, "shards": 2}})
    with db.session() as session, pytest.raises(ValidationError, match="exactly one shard"):
        execute_business(session, altered)
