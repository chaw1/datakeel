# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Complete production workflows through HTTP plans, human decisions and executed receipts."""

from collections.abc import Mapping
from pathlib import Path

from fastapi.testclient import TestClient

from datakeel.actions.models import ActionPlan, ActionRun
from datakeel.api.app import create_app
from datakeel.core.models import JsonDocument
from datakeel.core.production_models import ProductionProgress
from datakeel.ontology.models import FunctionResult
from datakeel.storage.database import Database
from tests.production_flow_support import action_payload, group_flow, personal_flow


class _HttpRunner:
    def __init__(self, client: TestClient) -> None:
        self.client = client

    def __call__(
        self, action: str, values: Mapping[str, object], actor: str = "local"
    ) -> JsonDocument:
        headers = {"X-Datakeel-Actor": actor}
        response = self.client.post(
            f"/api/actions/{action}/prepare",
            json=action_payload(action, values).root,
            headers=headers,
        )
        assert response.status_code == 200, response.text
        plan = ActionPlan.model_validate(response.json())
        if plan.requires_approval:
            approved = self.client.post(
                f"/api/approvals/{plan.id}",
                headers=headers,
                json={"approve": True, "plan_digest": plan.plan_digest, "actor": actor},
            )
            assert approved.status_code == 200, approved.text
            assert ActionPlan.model_validate(approved.json()).status == "APPROVED"
        request = {"plan_digest": plan.plan_digest, "actor": actor}
        executed = self.client.post(
            f"/api/actions/{plan.id}/execute", json=request, headers=headers
        )
        assert executed.status_code == 200, executed.text
        run = ActionRun.model_validate(executed.json())
        assert run.status == "SUCCEEDED"
        assert run.receipt is not None
        if "request_id" in plan.canonical_params:
            replay = self.client.post(
                f"/api/actions/{plan.id}/execute", json=request, headers=headers
            )
            assert replay.status_code == 200, replay.text
            assert ActionRun.model_validate(replay.json()) == run
        return JsonDocument.model_validate(run.receipt.quality["details"])


def test_http_personal_flow_imports_both_prediction_formats_and_finalizes(
    db: Database,
    tmp_path: Path,
) -> None:
    """Default zero-user HTTP actions preserve a personal workflow without assignments/reviews."""
    with TestClient(create_app(db)) as client:
        flow = personal_flow(db, tmp_path / "http-personal", _HttpRunner(client))
        response = client.get(
            "/api/production/objects/project", params={"object_id": flow.project.id}
        )
        assert response.status_code == 200, response.text
        assert len(FunctionResult.model_validate(response.json()).asset_refs) == 1
        progress = client.post(
            "/api/production/functions/project_progress", json={"project_id": flow.project.id}
        )
        assert progress.status_code == 200, progress.text
        value = ProductionProgress.model_validate(
            FunctionResult.model_validate(progress.json()).data
        )
        assert value.status == "finalized"
        assert flow.output_version is not None


def test_http_group_flow_applies_project_roles_and_retains_explicit_rework(
    db: Database,
    tmp_path: Path,
) -> None:
    """Registered annotator/reviewer identities can complete their project-bound workflow."""
    with TestClient(create_app(db)) as client:
        flow = group_flow(db, tmp_path / "http-group", _HttpRunner(client))
        for actor in ("local", "ann", "qa", "visitor"):
            response = client.post(
                "/api/production/functions/rework_rate",
                json={"project_id": flow.project.id},
                headers={"X-Datakeel-Actor": actor},
            )
            assert response.status_code == 200, response.text
        forbidden = client.post(
            "/api/actions/finalize_project/prepare",
            headers={"X-Datakeel-Actor": "ann"},
            json={"request_id": "forbidden-finalize", "project_id": flow.project.id},
        )
        assert forbidden.status_code == 403, forbidden.text
