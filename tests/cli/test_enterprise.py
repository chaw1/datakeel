# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Enterprise demo imports are controlled, repeatable, and respect semantic revisions."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from datakeel.actions import service as actions
from datakeel.actions.models import ActionRun, ExecuteRequest
from datakeel.cli import enterprise
from datakeel.core.errors import ExecutionError
from datakeel.core.models import JsonDocument, utcnow
from datakeel.storage.events import all_events
from datakeel.storage.metric_store import get_metric

if TYPE_CHECKING:
    from datakeel.storage.database import Database


def test_seed_when_repeated_uses_actions_and_preserves_user_metric_version(db: Database) -> None:
    """A second demo leaves imports unchanged and keeps a user's controlled metric edit."""
    first = enterprise.seed_enterprise_demo(db)
    assert first.table_count == 24
    assert first.column_count >= 100
    assert first.metric_count >= 12
    assert first.answer.status == "answered"
    assert all(item.plan_id and item.run_id for item in first.imports)
    metric = get_metric(db, "retail_revenue").definition
    changed = metric.model_copy(
        update={"measure": metric.measure.model_copy(update={"aggregation": "count"})}
    )
    plan = actions.prepare_action(
        db, "update_metric", JsonDocument({"definition": changed.model_dump(mode="json")})
    )
    run = actions.execute_plan(db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest))
    assert run.status == "SUCCEEDED"
    second = enterprise.seed_enterprise_demo(db)
    assert all(item.details.root["status"] == "unchanged" for item in second.imports)
    assert second.answer.metric_card is not None
    assert second.answer.metric_card.definition.version == 2
    assert second.answer.result != first.answer.result
    with db.session() as session:
        assert sum(event.operator == "CATALOG_IMPORT" for event in all_events(session)) == 4


def test_seed_when_controlled_import_fails_reports_failure(
    db: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Never proceed to semantic installation after a denied or failed source import."""

    def fail(*_args: object, **_kwargs: object) -> ActionRun:
        return ActionRun(
            id="failed",
            plan_id="failed",
            action_type="import_catalog",
            status="FAILED",
            created_at=utcnow(),
            error="Synthetic import failure",
        )

    monkeypatch.setattr(enterprise.actions, "execute_plan", fail)
    with pytest.raises(ExecutionError, match="Synthetic import failure"):
        enterprise.seed_enterprise_demo(db)
