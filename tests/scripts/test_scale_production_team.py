# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""B8 judges claim exclusivity from stored assignment windows, not client bookkeeping."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select

from datakeel.storage.production_reaper import reap_expired_leases
from datakeel.storage.production_rows import ProductionAssignmentRow
from scripts.scale_bench.production_seed import (
    claim_overlaps,
    register_annotators,
    run_action,
    seed_project,
)
from tests.production_team_ops import set_deadline

if TYPE_CHECKING:
    from datakeel.storage.database import Database


def test_claim_overlaps_counts_a_reclaim_once_and_flags_overlapping_holders(db: Database) -> None:
    """A reaped lease reclaimed by someone else is not a duplicate; overlapping windows are."""
    project_id = seed_project(db, 4, 1)
    register_annotators(db, project_id, ("annotator-a", "annotator-b"))
    first = run_action(db, "claim_task", {"project_id": project_id}, "annotator-a")
    set_deadline(db, str(first["id"]), -1)
    assert reap_expired_leases(db).released == 1
    second = run_action(db, "claim_task", {"project_id": project_id}, "annotator-b")
    assert second["id"] == first["id"]
    assert claim_overlaps(db, project_id) == {
        "assignment_rows": 2,
        "claimed_tasks": 1,
        "duplicate_claims": 0,
        "expired_then_claimed_again": 1,
    }
    with db.session() as session:
        row = session.scalars(
            select(ProductionAssignmentRow).where(ProductionAssignmentRow.actor == "annotator-a")
        ).one()
        row.payload = {**row.payload, "ended_at": "2999-01-01T00:00:00Z"}
        session.commit()
    assert claim_overlaps(db, project_id)["duplicate_claims"] == 1
