# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Complete production workflows through HTTP plans, human decisions and executed receipts."""

from collections.abc import Mapping
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from datakeel.actions.models import ActionPlan, ActionRun
from datakeel.api.app import create_app
from datakeel.core.models import JsonDocument
from datakeel.core.production_models import (
    AnnotationRevision,
    ProductionProgress,
    ProductionTask,
    Review,
)
from datakeel.ontology.models import FunctionResult
from datakeel.storage.database import Database
from datakeel.storage.production_queries import (
    get_project,
    get_task,
    list_assignments,
    list_reviews,
    list_revisions,
)
from tests.production_flow_support import action_payload, group_flow, personal_flow
from tests.production_helpers import production_fixture


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


def _denied_upgrade_action(
    client: TestClient,
    action: str,
    values: Mapping[str, object],
    actor: str,
    status: int,
) -> None:
    headers = {"X-Datakeel-Actor": actor}
    prepared = client.post(
        f"/api/actions/{action}/prepare",
        headers=headers,
        json=action_payload(action, values).root,
    )
    assert prepared.status_code == 200, prepared.text
    plan = ActionPlan.model_validate(prepared.json())
    assert not plan.requires_approval
    result = client.post(
        f"/api/actions/{plan.id}/execute",
        headers=headers,
        json={"plan_digest": plan.plan_digest, "actor": actor},
    )
    assert result.status_code == status, result.text


def _assert_upgrade_takeover_denied(client: TestClient, task: ProductionTask) -> None:
    annotation = {"sample_id": task.sample_id, "annotator_id": "other", "labels": ["cat"]}
    _denied_upgrade_action(
        client,
        "save_revision",
        {
            "task_id": task.id,
            "previous_revision_id": task.latest_revision_id,
            "annotation": annotation,
        },
        "other",
        403,
    )
    for action in ("submit_task", "release_task"):
        _denied_upgrade_action(client, action, {"task_id": task.id}, "other", 403)
    _denied_upgrade_action(
        client, "assign_tasks", {"task_ids": [task.id], "actor": "other"}, "local", 409
    )
    _denied_upgrade_action(client, "claim_task", {"project_id": task.project_id}, "other", 404)


def _author_save(runner: _HttpRunner, task: ProductionTask) -> AnnotationRevision:
    result = runner(
        "save_revision",
        {
            "task_id": task.id,
            "previous_revision_id": task.latest_revision_id,
            "annotation": {
                "sample_id": task.sample_id,
                "annotator_id": "author",
                "labels": ["cat"],
            },
        },
        "author",
    )
    return AnnotationRevision.model_validate(result.root, extra="ignore")


@pytest.mark.parametrize("resume", ["submit", "save"])
def test_http_personal_upgrade_resumes_author_then_reviews_and_finalizes(
    db: Database, resume: str
) -> None:
    """A saved personal task finishes through signed receipts without a synthetic rework round."""
    project, tasks = production_fixture(db, count=1)
    task = tasks[0]
    with TestClient(create_app(db)) as client:
        runner = _HttpRunner(client)
        runner("manage_users", {"operation": "create", "user_id": "local"})
        for actor, role in (("author", "annotator"), ("other", "annotator"), ("qa", "reviewer")):
            runner("manage_users", {"operation": "create", "user_id": actor, "role_ids": [role]})
        first = _author_save(runner, task)
        assert list_assignments(db, task.id) == ()
        upgraded = runner("upgrade_project", {"project_id": project.id, "workflow_tier": "group"})
        assert upgraded.root["workflow_tier"] == "group"
        retained = get_task(db, task.id)
        assert (retained.state, retained.round, retained.annotator_id) == (
            "in_progress",
            0,
            "author",
        )
        _assert_upgrade_takeover_denied(client, retained)
        head = _author_save(runner, retained) if resume == "save" else first
        submitted = runner("submit_task", {"task_id": task.id}, "author")
        assert (submitted.root["state"], submitted.root["round"]) == ("submitted", 0)
        claimed = runner("claim_task", {"project_id": project.id, "stage": "review"}, "qa")
        assert (claimed.root["state"], claimed.root["round"]) == ("in_review", 0)
        review = Review.model_validate(
            runner(
                "review_task",
                {"task_id": task.id, "revision_id": head.id, "decision": "approve"},
                "qa",
            ).root
        )
        assert (review.actor, review.revision_id, review.round) == ("qa", head.id, 0)
        finalized = runner("finalize_project", {"project_id": project.id})
        assert finalized.root["revision_ids"] == [head.id]
        assert finalized.root["produced_by_project"] == project.id
        assert finalized.root["source_version_id"] == project.version_id
        assert finalized.root["batch_id"]
        assert get_project(db, project.id).finalized_version_id == finalized.root["version_id"]
    finished = get_task(db, task.id)
    assert (finished.state, finished.round, finished.approved_revision_id) == (
        "finalized",
        0,
        head.id,
    )
    revisions = list_revisions(db, task.id)
    assert revisions[0] == first
    assert revisions == ((first, head) if resume == "save" else (first,))
    assert head.previous_revision_id == (first.id if resume == "save" else None)
    assert list_reviews(db, task.id) == (review,)
    assignments = list_assignments(db, task.id)
    assert {(item.actor, item.stage) for item in assignments} == {
        ("author", "annotation"),
        ("qa", "review"),
    }
    assert all(not item.active for item in assignments)
