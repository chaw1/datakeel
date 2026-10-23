# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Recovery uses typed SSE and rejects forged authorization before response headers."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from datakeel.actions.models import ApprovalDecision
from datakeel.actions.service import approve_plan, list_runs
from datakeel.agent.providers import FakeProvider
from datakeel.agent.service import get_conversation
from datakeel.core.agent_models import ConversationAudit, ModelResponse
from tests.agent.test_resume import ForgedCase, forge_approval, pause_deletion
from tests.api.test_agent import agent_client, events

if TYPE_CHECKING:
    from datakeel.storage.database import Database
    from tests.asgi_client import TestClient


__all__ = ["agent_client"]


@pytest.mark.parametrize(
    "case", ["no_approval", "digest_mismatch", "expired", "actor_mismatch", "foreign_plan"]
)
def test_resume_when_authorization_forged_returns_403_and_queryable_denial(
    db: Database,
    agent_client: tuple[TestClient, str],
    case: ForgedCase,
) -> None:
    """Each forgery returns a domain error before any successful SSE response is started."""
    client, dataset_id = agent_client
    conversation_id, plan = pause_deletion(db, dataset_id)
    requested = plan
    if case == "foreign_plan":
        _, requested = pause_deletion(db, dataset_id)
        approve_plan(
            db, requested.id, ApprovalDecision(approve=True, plan_digest=requested.plan_digest)
        )
    elif case != "no_approval":
        forge_approval(db, plan, case)
    before = get_conversation(db, conversation_id)
    response = client.post(
        f"/api/agent/conversations/{conversation_id}/resume",
        json={"plan_id": requested.id, "idempotency_key": case},
    )
    assert response.status_code == 403, response.text
    assert response.headers["content-type"].startswith("application/json")
    audit_response = client.get(f"/api/agent/conversations/{conversation_id}/audit")
    assert audit_response.status_code == 200
    audit = [ConversationAudit.model_validate(entry) for entry in audit_response.json()]
    assert len(audit) == 1
    assert audit[0].kind == "RESUME_DENIED"
    assert audit[0].plan_id == requested.id
    assert audit[0].conversation_id == conversation_id
    assert audit[0].reason
    assert get_conversation(db, conversation_id).messages == before.messages
    assert list_runs(db) == []


def test_resume_when_approved_streams_receipt_and_replays_without_second_execution(
    db: Database,
    agent_client: tuple[TestClient, str],
) -> None:
    """A human approval resumes the existing response while retaining exact event replay."""
    client, dataset_id = agent_client
    conversation_id, plan = pause_deletion(db, dataset_id)
    before = get_conversation(db, conversation_id)
    provider = FakeProvider([ModelResponse(content="Recovered over HTTP.")])
    client.app.state.agent_provider = provider
    approval = client.post(
        f"/api/approvals/{plan.id}", json={"approve": True, "plan_digest": plan.plan_digest}
    )
    assert approval.status_code == 200
    url = f"/api/agent/conversations/{conversation_id}/resume"
    body = {"plan_id": plan.id, "idempotency_key": "separate-response-key"}
    first = events(client.post(url, json=body))
    assert [event.event for event in first] == ["receipt", "text", "done"]
    assert events(client.post(url, json=body)) == first
    assert len(provider.requests) == 1
    assert len(list_runs(db)) == 1
    assert get_conversation(db, conversation_id).messages[:-1] == before.messages
    audit = client.get(f"/api/agent/conversations/{conversation_id}/audit").json()
    assert [entry["kind"] for entry in audit] == ["RESUME_AUTHORIZED"]
    assert client.post(url, json={**body, "plan_id": "different-plan"}).status_code == 409


def test_resume_when_missing_or_extra_authorization_payload_rejects_typed_input(
    db: Database,
    agent_client: tuple[TestClient, str],
) -> None:
    """The recovery payload accepts only plan identity and its idempotency key."""
    client, dataset_id = agent_client
    conversation_id, plan = pause_deletion(db, dataset_id)
    url = f"/api/agent/conversations/{conversation_id}/resume"
    for extra in ({"approve": True}, {"actor": "local"}, {"plan_digest": plan.plan_digest}):
        response = client.post(
            url, json={"plan_id": plan.id, "idempotency_key": "forged-extra", **extra}
        )
        assert response.status_code == 422
    for body in (
        {"idempotency_key": "missing-plan"},
        {"plan_id": "", "idempotency_key": "empty-plan"},
        {"plan_id": plan.id, "idempotency_key": ""},
    ):
        assert client.post(url, json=body).status_code == 422
    assert client.get(f"/api/agent/conversations/{conversation_id}/audit").json() == []
    schema = client.get("/api/openapi.json").json()
    resume_schema = schema["components"]["schemas"]["ResumeInput"]
    assert set(resume_schema["properties"]) == {"plan_id", "idempotency_key"}
    assert resume_schema["additionalProperties"] is False
    assert "/api/agent/conversations/{conversation_id}/resume" in schema["paths"]
    assert "/api/agent/conversations/{conversation_id}/audit" in schema["paths"]


def test_resume_when_conversation_missing_returns_404_before_stream(
    agent_client: tuple[TestClient, str],
) -> None:
    """Unknown conversation identities preserve the existing HTTP not-found boundary."""
    client, _ = agent_client
    response = client.post(
        "/api/agent/conversations/missing/resume",
        json={"plan_id": "missing", "idempotency_key": "missing"},
    )
    assert response.status_code == 404
    assert client.get("/api/agent/conversations/missing/audit").status_code == 404


def test_recovery_routes_when_old_prefix_used_are_unavailable(
    db: Database,
    agent_client: tuple[TestClient, str],
) -> None:
    """Removed routes cannot resume an approved plan or expose its recovery audit."""
    client, dataset_id = agent_client
    conversation_id, plan = pause_deletion(db, dataset_id)
    approve_plan(db, plan.id, ApprovalDecision(approve=True, plan_digest=plan.plan_digest))
    response = client.post(
        f"/api/conversations/{conversation_id}/resume",
        json={"plan_id": plan.id, "idempotency_key": "removed-prefix"},
    )
    assert response.status_code in {404, 405}
    assert client.get(f"/api/conversations/{conversation_id}/audit").status_code == 404
    assert list_runs(db) == []
    assert client.get(f"/api/agent/conversations/{conversation_id}/audit").json() == []
    paths = client.get("/api/openapi.json").json()["paths"]
    assert "/api/conversations/{conversation_id}/resume" not in paths
    assert "/api/conversations/{conversation_id}/audit" not in paths
