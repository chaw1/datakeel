# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Evidence membership freezes once while selected file versions and state stay protected."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from datakeel.actions.models import ExecuteRequest
from datakeel.actions.parameters import parse_params
from datakeel.actions.service import execute_plan, prepare_action
from datakeel.core.errors import ConflictError
from datakeel.core.models import JsonDocument
from datakeel.ontology.models import AssertionFilter, ObjectSet, PropertyFilter
from datakeel.storage.action_snapshot import current_snapshot_digest
from datakeel.storage.database import DatasetRow, VersionRow
from datakeel.storage.evidence_queries import get_evidence
from datakeel.storage.evidence_store import list_assertions
from datakeel.storage.object_queries import evaluate
from tests.evidence.interface_fixtures import seed_query_evidence

if TYPE_CHECKING:
    from pathlib import Path

    from datakeel.actions.models import ActionPlan
    from datakeel.storage.database import Database


def _prepare_selection(db: Database, dataset_id: str, predicate: str = "label_gap") -> ActionPlan:
    selection = ObjectSet(
        dataset_id=dataset_id,
        split="val",
        assertion_filters=[
            AssertionFilter(predicate="label_gap", concept="person", value="present")
        ]
        if predicate == "label_gap"
        else [],
        has_near_duplicate_in="train" if predicate == "near_duplicate_of" else None,
    )
    return prepare_action(
        db,
        "create_version_from_selection",
        JsonDocument({"selection": selection.model_dump(mode="json")}),
    )


@pytest.mark.parametrize("predicate", ["label_gap", "near_duplicate_of"])
def test_selection_when_assertion_rejected_keeps_exact_frozen_membership(
    db: Database, tmp_path: Path, predicate: str
) -> None:
    """Review changes cannot remove already selected samples or replace their source versions."""
    dataset_id = seed_query_evidence(db, tmp_path / "samples")
    plan = _prepare_selection(db, dataset_id, predicate)
    assert len(plan.manifest.objects) == 1
    original = plan.manifest.objects[0]
    assertion = next(
        item
        for item in get_evidence(db, original.asset_ref.asset_id).assertions
        if item.predicate == predicate
    )
    decision = prepare_action(
        db,
        "decide_assertions",
        JsonDocument({"assertion_ids": [assertion.id], "status": "rejected"}),
    )
    execute_plan(db, decision.id, ExecuteRequest(plan_digest=decision.plan_digest))
    assert evaluate(db, plan.manifest.query).objects == []
    with db.session() as session:
        params = parse_params(plan.action_type, JsonDocument(plan.canonical_params))
        assert current_snapshot_digest(session, plan, params) == plan.state_digest
    result = execute_plan(db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest))
    assert result.status == "SUCCEEDED"
    assert result.receipt is not None
    output = next(ref for ref in result.receipt.outputs if ref.asset_type == "version")
    with db.session() as session:
        created = session.get(VersionRow, output.asset_id)
        source = session.get(VersionRow, original.asset_ref.version)
        assert created is not None
        assert source is not None
        assert created.manifest == [
            item for item in source.manifest if item["id"] == original.asset_ref.asset_id
        ]
    assert any(
        item.id == assertion.id and item.status == "rejected" for item in list_assertions(db)
    )


@pytest.mark.parametrize("change", ["file_state", "quality"])
def test_selection_when_frozen_file_state_or_quality_changes_rejects_execution(
    db: Database, tmp_path: Path, change: str
) -> None:
    """Freezing evidence membership never authorizes stale file revisions or quality facts."""
    dataset_id = seed_query_evidence(db, tmp_path / "samples")
    plan = _prepare_selection(db, dataset_id)
    if change == "file_state":
        quarantine = prepare_action(
            db,
            "quarantine_files",
            JsonDocument(
                {
                    "selection": ObjectSet(
                        dataset_id=dataset_id,
                        filters=[
                            PropertyFilter(
                                field="id", value=plan.manifest.objects[0].asset_ref.asset_id
                            )
                        ],
                    ).model_dump(mode="json")
                }
            ),
        )
        execute_plan(db, quarantine.id, ExecuteRequest(plan_digest=quarantine.plan_digest))
    else:
        with db.session() as session:
            dataset = session.get(DatasetRow, dataset_id)
            assert dataset is not None
            dataset.quality_config = {"min_image_width": 10000}
            session.commit()
    with pytest.raises(ConflictError, match="target state changed"):
        execute_plan(db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest))
