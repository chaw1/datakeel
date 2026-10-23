# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Routing suggestions are replayable observations with narrowly scoped input prefills."""

from pathlib import Path

import pytest

from datakeel.actions.models import ApprovalDecision
from datakeel.actions.service import approve_plan
from datakeel.agent.providers import FakeProvider
from datakeel.agent.service import resume_conversation
from datakeel.api.app import create_app
from datakeel.core.agent_models import ModelResponse, ResumeInput
from datakeel.harness.service import list_traces
from datakeel.storage.database import Database
from datakeel.storage.dataset_service import import_paths
from tests.agent.test_resume import pause_deletion
from tests.api.test_agent import events
from tests.asgi_client import TestClient


def test_route_api_when_messages_finish_persists_candidates_branch_and_dataset(
    db: Database, tmp_path: Path
) -> None:
    """Suggestions add no workflow run and never infer arbitrary workflow inputs from prose."""
    source = tmp_path / "local.txt"
    source.write_text("Generated local data.")
    dataset = import_paths(db, "routing-fixture", [source])
    app = create_app(db)
    app.state.agent_provider = FakeProvider([ModelResponse(content="Acknowledged.")])
    with TestClient(app) as client:
        session = client.post(
            "/api/agent/conversations", json={"dataset_id": dataset.id, "model": "fake-script"}
        ).json()
        url = f"/api/agent/conversations/{session['id']}"
        request = {
            "content": "Please run a dataset health check with quality_max=25",
            "idempotency_key": "route-replay",
        }
        streamed = events(client.post(f"{url}/messages", json=request))
        assert [event.event for event in streamed] == ["text", "route", "done"]
        decision = client.get(f"{url}/routes").json()[0]
        assert decision["workflow_id"] == "dataset-health"
        assert decision["branch"] == "keyword"
        assert decision["inputs"] == {"dataset_id": dataset.id}
        assert decision["score"] == 1
        assert len(decision["candidates"]) == 3
        assert streamed[-1].model_routes[0].pinned is True
        assert events(client.post(f"{url}/messages", json=request)) == streamed
        assert len(client.get(f"{url}/routes").json()) == 1
        assert client.get("/api/agent/conversations/missing/routes").status_code == 404
        assert client.get("/api/workflows/runs").json() == []


def test_resume_when_approved_never_reclassifies_previous_message(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Resuming a durable approval checkpoint only reports its new model attempts."""
    source = tmp_path / "empty.txt"
    source.write_text("")
    dataset = import_paths(db, "resume-routing", [source])
    conversation, plan = pause_deletion(db, dataset.id)
    approve_plan(db, plan.id, ApprovalDecision(approve=True, plan_digest=plan.plan_digest))
    before = len(list_traces(db, conversation))

    def unexpected(*_args: object) -> None:
        pytest.fail("Resume must not invoke intent routing")

    monkeypatch.setattr("datakeel.agent.service.route_message", unexpected)
    resumed = list(
        resume_conversation(
            db,
            conversation,
            ResumeInput(plan_id=plan.id, idempotency_key="resume-routing"),
            provider=FakeProvider([ModelResponse(content="Resumed.")]),
        )
    )
    assert [event.event for event in resumed] == ["receipt", "text", "done"]
    assert all(event.route is None for event in resumed)
    assert len(resumed[-1].model_routes) == 1
    assert len(list_traces(db, conversation)) == before + 1
