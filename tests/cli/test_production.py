# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Production CLI parsing and dispatch complete personal and registered group workflows."""

from collections.abc import Mapping
from pathlib import Path

import pytest

from datakeel.actions.models import ActionPlan, ActionRun
from datakeel.cli import parser
from datakeel.cli.production import dispatch
from datakeel.core.models import JsonDocument, new_id
from datakeel.core.production_models import ProductionProgress
from datakeel.ontology.models import FunctionResult
from datakeel.storage.database import Database
from tests.production_flow_support import action_payload, group_flow, personal_flow


class _CliRunner:
    def __init__(self, db: Database, directory: Path, output: pytest.CaptureFixture[str]) -> None:
        self.db = db
        self.directory = directory
        self.output = output

    def _dispatch(self, *arguments: str) -> str:
        dispatch(self.db, parser().parse_args(["production", *arguments]))
        return self.output.readouterr().out

    def __call__(
        self, action: str, values: Mapping[str, object], actor: str = "local"
    ) -> JsonDocument:
        path = self.directory / (new_id() + ".json")
        path.write_text(action_payload(action, values).model_dump_json(), encoding="utf-8")
        plan = ActionPlan.model_validate_json(
            self._dispatch("prepare", action, str(path), "--actor", actor)
        )
        if plan.requires_approval:
            approved = ActionPlan.model_validate_json(
                self._dispatch("approve", plan.id, "--digest", plan.plan_digest, "--actor", actor)
            )
            assert approved.status == "APPROVED"
        run = ActionRun.model_validate_json(
            self._dispatch("execute", plan.id, "--digest", plan.plan_digest, "--actor", actor)
        )
        assert run.status == "SUCCEEDED"
        assert run.receipt is not None
        if "request_id" in plan.canonical_params:
            replay = ActionRun.model_validate_json(
                self._dispatch("execute", plan.id, "--digest", plan.plan_digest, "--actor", actor)
            )
            assert replay == run
        return JsonDocument.model_validate(run.receipt.quality["details"])

    def progress(self, project_id: str, actor: str) -> ProductionProgress:
        """Read final counters through the actual CLI function command."""
        path = self.directory / "read.json"
        path.write_text(
            JsonDocument({"project_id": project_id}).model_dump_json(), encoding="utf-8"
        )
        result = FunctionResult.model_validate_json(
            self._dispatch("read", "project_progress", str(path), "--actor", actor)
        )
        return ProductionProgress.model_validate(result.data)


def test_cli_personal_flow_prepares_approves_imports_and_finalizes(
    db: Database,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The installed grammar reaches every personal production action and explicit approval."""
    runner = _CliRunner(db, tmp_path, capsys)
    flow = personal_flow(db, tmp_path / "cli-personal", runner)
    assert runner.progress(flow.project.id, "local").status == "finalized"


def test_cli_group_flow_uses_real_actors_project_roles_and_review_rounds(
    db: Database,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The same terminal commands carry registered identities through assignment and rework."""
    runner = _CliRunner(db, tmp_path, capsys)
    flow = group_flow(db, tmp_path / "cli-group", runner)
    assert runner.progress(flow.project.id, "qa").status == "finalized"
