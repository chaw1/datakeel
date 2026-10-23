# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Previously frozen ObjectSet 1.0 plans keep their digest and execution behavior."""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING

from datakeel.actions.models import ActionPlan, ExecuteRequest
from datakeel.actions.parameters import ExportParams
from datakeel.actions.policy import digest, plan_digest
from datakeel.actions.service import execute_plan, prepare_action
from datakeel.core.models import JsonDocument
from datakeel.core.settings import get_settings
from datakeel.ontology.models import ObjectSet
from datakeel.storage.action_rows import ActionPlanRow
from datakeel.storage.action_snapshot import snapshot_digest
from datakeel.storage.dataset_service import list_files
from datakeel.storage.object_queries import evaluate_in_session

if TYPE_CHECKING:
    from datakeel.storage.database import Database
    from tests.actions.conftest import DatasetFixture


def test_stored_legacy_plan_without_new_fields_keeps_digest_and_executes(
    db: Database, dataset: DatasetFixture
) -> None:
    """Replay the old wire shape through storage, authorization, and current selection."""
    created, _ = dataset
    plan = prepare_action(
        db,
        "quarantine_files",
        JsonDocument({"selection": {"schema_version": "1.0", "dataset_id": created.id}}),
    )
    legacy = plan.model_dump(mode="json")
    legacy.pop("operation_id")
    query = legacy["manifest"]["query"]
    expected_fields = {
        "schema_version",
        "object_type",
        "namespace",
        "dataset_id",
        "filters",
        "quality_min",
        "quality_max",
        "version_ids",
        "created_after",
        "created_before",
        "include_deleted",
        "limit",
    }
    assert set(query) == expected_fields
    assert set(legacy["canonical_params"]["selection"]) == expected_fields
    legacy["plan_digest"] = digest(
        {key: value for key, value in legacy.items() if key not in {"plan_digest", "status"}}
    )
    with db.session() as session:
        row = session.get(ActionPlanRow, plan.id)
        assert row is not None
        row.payload = legacy
        session.commit()
    restored = ActionPlan.model_validate(legacy)
    assert restored.operation_id is None
    assert plan_digest(restored) == legacy["plan_digest"]
    result = execute_plan(db, plan.id, ExecuteRequest(plan_digest=legacy["plan_digest"]))
    assert result.status == "SUCCEEDED"
    assert all(item.metadata["quarantined"] for item in list_files(db, created.id))


def test_legacy_export_snapshot_keeps_supplemental_dataset_query_version(
    db: Database, dataset: DatasetFixture
) -> None:
    """A pending 1.0 export keeps its old supplementary dataset-state digest."""
    created, _ = dataset
    with db.session() as session:
        files = evaluate_in_session(session, ObjectSet(schema_version="1.0", dataset_id=created.id))
        metadata = evaluate_in_session(
            session, ObjectSet(schema_version="1.0", object_type="dataset", dataset_id=created.id)
        )
        previous = hashlib.sha256(
            json.dumps(
                [files.state_digest, metadata.state_digest, get_settings().base_url],
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        assert snapshot_digest(session, ExportParams(dataset_id=created.id), files) == previous
