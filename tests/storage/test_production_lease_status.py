# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""The lease status read reports the deadline that is actually enforced."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from datakeel.actions.production_parameters import UpgradeProjectParams
from datakeel.core.models import JsonDocument, new_id, utcnow
from datakeel.core.production_team_models import LeaseStatus
from datakeel.ontology.functions import invoke_function
from datakeel.storage.production_projects import upgrade_project
from datakeel.storage.production_rows import ProductionAssignmentRow
from tests.production_helpers import production_fixture
from tests.production_team_ops import claim, heartbeat, set_deadline

if TYPE_CHECKING:
    from datakeel.storage.database import Database


def _status(db: Database, project_id: str) -> LeaseStatus:
    result = invoke_function(db, "lease_status", JsonDocument({"project_id": project_id}))
    return LeaseStatus.model_validate(result.data)


def _column(db: Database, assignment_id: str) -> datetime:
    with db.session() as session:
        row = session.get(ProductionAssignmentRow, assignment_id)
        assert row is not None
        assert row.lease_expires_at is not None
        return datetime.fromtimestamp(row.lease_expires_at, tz=UTC)


def test_lease_status_after_upgrade_reports_the_enforced_deadline(db: Database) -> None:
    """A group claim's stale recorded expiry is replaced by the deadline the upgrade started."""
    project, _tasks = production_fixture(db, "group", count=1)
    task = claim(db, project.id, "annotator-a")
    stale = set_deadline(db, task.id, -1800).lease_expires_at
    with db.session() as session:
        db.lock_writes(session)
        upgrade_project(
            session,
            UpgradeProjectParams(request_id=new_id(), project_id=project.id, workflow_tier="team"),
        )
        session.commit()
    status = _status(db, project.id)
    assert status.overdue == ()
    [view] = status.active
    enforced = _column(db, view.assignment.id)
    assert view.assignment.lease_expires_at == enforced
    assert view.assignment.lease_expires_at != stale
    assert view.assignment.lease_expires_at > utcnow() + timedelta(
        minutes=project.lease_minutes - 1
    )
    expected = (enforced - status.observed_at).total_seconds()
    assert abs(view.seconds_remaining - expected) < 1e-3
    renewed = heartbeat(db, task.id, "annotator-a")
    assert _status(db, project.id).active[0].assignment.lease_expires_at == renewed.lease_expires_at
