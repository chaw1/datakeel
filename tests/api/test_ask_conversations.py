# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Question threads preserve owner boundaries, current grants and durable replay."""

from datetime import timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from datakeel.api.app import create_app
from datakeel.core.ask_conversation_models import AskConversation
from datakeel.core.ask_models import AskAnswer
from datakeel.core.data_asset_models import (
    AssetApplicationInput,
    AssetMutationContext,
    DataAssetDefinition,
)
from datakeel.core.models import AssetRef, new_id, utcnow
from datakeel.storage.data_asset_grants import (
    decide_application_in_session,
    revoke_grant_in_session,
    submit_application,
)
from datakeel.storage.data_asset_store import create_asset_in_session, set_status_in_session
from datakeel.storage.database import Database
from tests.enterprise_support import enterprise_fixture

REFERENCE = "2026-10-01T00:00:00Z"
QUESTION = "上个季度华东区零售额是多少"


def _question(client: TestClient, text: str, conversation: str | None = None) -> AskAnswer:
    response = client.post(
        "/api/ask",
        json={
            "question": text,
            "reference_instant": REFERENCE,
            "conversation_id": conversation,
        },
    )
    assert response.status_code == 200, response.text
    return AskAnswer.model_validate(response.json())


def _context() -> AssetMutationContext:
    return AssetMutationContext(actor="steward", operation_id=new_id())


def _protect_metric_and_grant(db: Database) -> str:
    with db.session() as session:
        asset = create_asset_in_session(
            session,
            DataAssetDefinition(
                name="Protected generated revenue",
                owner="steward",
                classification="restricted",
                target=AssetRef(asset_type="metric", asset_id="retail_revenue"),
            ),
            _context(),
        )
        set_status_in_session(session, asset.id, "published", _context())
        session.commit()
    application = submit_application(
        db,
        AssetApplicationInput(
            asset_id=asset.id,
            purpose="Generated thread regression",
            scopes=("query",),
            expires_at=utcnow() + timedelta(days=1),
        ),
        "local-user",
    )
    with db.session() as session:
        decided = decide_application_in_session(session, application.id, _context(), approved=True)
        session.commit()
    assert decided.grant_id is not None
    return decided.grant_id


def test_http_thread_restores_turns_and_deletes_saved_replay(db: Database, tmp_path: Path) -> None:
    """A process rebuild recovers the same frame; deletion removes answer lookup too."""
    enterprise_fixture(db, tmp_path / "enterprise")
    client = TestClient(create_app(db))
    created = client.post("/api/ask/conversations")
    assert created.status_code == 200
    conversation = AskConversation.model_validate(created.json())
    assert not conversation.turns
    first = _question(client, QUESTION, conversation.id)
    follow = _question(client, "那华南呢", conversation.id)
    equivalent = _question(client, "上个季度华南区零售额是多少")
    assert follow.result == equivalent.result
    assert first.conversation_id == follow.conversation_id == conversation.id
    assert all(item.interpreted_question for item in (first, follow))
    restarted = TestClient(create_app(db))
    restored = AskConversation.model_validate(
        restarted.get(f"/api/ask/conversations/{conversation.id}").json()
    )
    assert [turn.id for turn in restored.turns] == [first.id, follow.id]
    assert conversation.id in {
        item["id"] for item in restarted.get("/api/ask/conversations").json()
    }
    assert restarted.delete(f"/api/ask/conversations/{conversation.id}").status_code == 204
    assert restarted.get(f"/api/ask/conversations/{conversation.id}").status_code == 404
    assert restarted.get(f"/api/ask/{first.id}").status_code == 404
    assert restarted.get(f"/api/ask/{follow.id}").status_code == 404


def test_http_thread_owner_applies_to_followup_history_delete_and_replay(db: Database) -> None:
    """A different actor cannot use a known thread ID to disclose or mutate its history."""
    client = TestClient(create_app(db))
    first = _question(client, "unknown generated measure")
    other = TestClient(create_app(db), headers={"X-Datakeel-Actor": "other"})
    path = f"/api/ask/conversations/{first.conversation_id}"
    assert other.get("/api/ask/conversations").json() == []
    assert other.get(path).status_code == 404
    assert other.delete(path).status_code == 404
    assert other.get(f"/api/ask/{first.id}").status_code == 404
    response = other.post(
        "/api/ask", json={"question": "那华南呢", "conversation_id": first.conversation_id}
    )
    assert response.status_code == 404
    assert client.get(path).status_code == 200


def test_http_thread_header_actor_overrides_legacy_body_actor(db: Database) -> None:
    """Question ownership matches the header used for CRUD, retaining old body defaults."""
    client = TestClient(create_app(db), headers={"X-Datakeel-Actor": "header-reader"})
    response = client.post(
        "/api/ask", json={"question": "unknown generated measure", "actor": "body-reader"}
    )
    assert response.status_code == 200
    answer = AskAnswer.model_validate(response.json())
    restored = client.get(f"/api/ask/conversations/{answer.conversation_id}")
    assert restored.status_code == 200
    assert restored.json()["actor"] == "header-reader"
    assert TestClient(create_app(db)).get(f"/api/ask/{answer.id}").status_code == 404


def test_http_revoked_grant_blocks_followup_replay_and_history_disclosure(
    db: Database, tmp_path: Path
) -> None:
    """A formerly readable answer never becomes an authorization cache for later turns."""
    enterprise_fixture(db, tmp_path / "enterprise")
    grant = _protect_metric_and_grant(db)
    client = TestClient(create_app(db))
    first = _question(client, QUESTION)
    assert first.status == "answered"
    path = f"/api/ask/conversations/{first.conversation_id}"
    assert client.get(path).status_code == 200
    with db.session() as session:
        revoke_grant_in_session(session, grant, _context())
        session.commit()
    follow = client.post(
        "/api/ask", json={"question": "那华南呢", "conversation_id": first.conversation_id}
    )
    assert follow.status_code == 403
    assert client.get(f"/api/ask/{first.id}").status_code == 403
    assert client.get(path).status_code == 403
    assert client.get("/api/ask/conversations").json() == []
    assert client.delete(path).status_code == 204


def test_http_openapi_preserves_legacy_ask_fields_and_adds_thread_routes(db: Database) -> None:
    """Old required fields and paths remain usable with an optional thread identifier."""
    schema = create_app(db).openapi()
    request = schema["components"]["schemas"]["AskRequest"]
    assert request["required"] == ["question"]
    assert {
        "question",
        "metric_id",
        "subject_id",
        "knowledge_intent",
        "session_id",
        "reference_instant",
        "actor",
        "conversation_id",
    } <= request["properties"].keys()
    assert {"get"} <= schema["paths"]["/api/ask/{answer_id}"].keys()
    assert {"post"} <= schema["paths"]["/api/ask"].keys()
    assert {"get", "post"} <= schema["paths"]["/api/ask/conversations"].keys()
    assert {"get", "delete"} <= schema["paths"]["/api/ask/conversations/{conversation_id}"].keys()
