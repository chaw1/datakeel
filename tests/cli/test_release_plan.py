# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""The CLI prepares large releases with an explicit budget shown in the approved plan."""

import json
from pathlib import Path

import pytest

from datakeel.actions.models import ActionPlan, ActionRun
from datakeel.core.errors import BudgetError, ValidationError
from datakeel.storage.database import Database
from tests.api.release_budget_helpers import FILES, large_version
from tests.cli.conftest import Invoke


def test_cli_release_plan_requests_budget_and_executes(
    db: Database, tmp_path: Path, invoke: Invoke, capsys: pytest.CaptureFixture[str]
) -> None:
    """Default budget refuses; an explicit budget is frozen, approved and executed."""
    dataset, version = large_version(db, tmp_path)
    params = tmp_path / "release.json"
    params.write_text(
        json.dumps({"dataset_id": dataset, "version_id": version, "tag": "1.0.0"}), encoding="utf-8"
    )
    with pytest.raises(BudgetError, match="max_objects"):
        invoke("release-plan", "prepare", "publish_release", str(params))
    with pytest.raises(ValidationError, match="above the ceiling"):
        invoke(
            "release-plan", "prepare", "publish_release", str(params), "--max-objects", "2000000"
        )
    invoke("release-plan", "prepare", "publish_release", str(params), "--max-objects", "20000")
    plan = ActionPlan.model_validate_json(capsys.readouterr().out)
    assert plan.context.max_objects == 20_000
    assert plan.impact.object_count == FILES
    invoke("release-plan", "approve", plan.id, "--digest", plan.plan_digest)
    assert ActionPlan.model_validate_json(capsys.readouterr().out).status == "APPROVED"
    invoke("release-plan", "execute", plan.id, "--digest", plan.plan_digest)
    run = ActionRun.model_validate_json(capsys.readouterr().out)
    assert run.status == "SUCCEEDED"
