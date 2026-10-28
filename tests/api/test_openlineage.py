# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Only explicitly authenticated OpenLineage producers can append external facts."""

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from datakeel.api.errors import register_errors
from datakeel.api.routes.openlineage import router
from datakeel.core.models import JsonDocument
from datakeel.storage.database import Database
from datakeel.storage.events import all_events

FIXTURE = Path(__file__).parents[1] / "fixtures" / "metadata" / "openlineage.json"


def client(db: Database) -> TestClient:
    """Use the production router with an isolated database and shared error mapping."""
    app = FastAPI()
    app.state.db = db
    register_errors(app)
    app.include_router(router)
    return TestClient(app)


@pytest.mark.parametrize("configured", [False, True])
@pytest.mark.parametrize("header", [None, "Bearer incorrect", "Basic invalid"])
def test_openlineage_missing_or_invalid_auth_rejects_without_write(
    db: Database, monkeypatch: pytest.MonkeyPatch, *, configured: bool, header: str | None
) -> None:
    """Unconfigured ingestion and invalid credentials always fail closed."""
    monkeypatch.delenv("DATAKEEL_OPENLINEAGE_TOKEN", raising=False)
    if configured:
        monkeypatch.setenv("DATAKEEL_OPENLINEAGE_TOKEN", "fixture-ingestion-token")
    headers = {"Authorization": header} if header else {}
    response = client(db).post(
        "/api/openlineage/events",
        headers=headers,
        json=JsonDocument.model_validate_json(FIXTURE.read_text()).root,
    )
    assert response.status_code == 403
    with db.session() as session:
        assert all_events(session) == []


def test_openlineage_authenticated_standard_event_and_duplicate_return_receipt(
    db: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Configured bearer credentials permit ingestion and expose idempotent receipts."""
    monkeypatch.setenv("DATAKEEL_OPENLINEAGE_TOKEN", "fixture-ingestion-token")
    monkeypatch.setenv(
        "DATAKEEL_OPENLINEAGE_NAMESPACES",
        '{"postgres://warehouse.example":{"source_id":"warehouse","database":"analytics"}}',
    )
    payload = JsonDocument.model_validate_json(FIXTURE.read_text()).root
    headers = {"Authorization": "Bearer fixture-ingestion-token"}
    http = client(db)
    first = http.post("/api/openlineage/events", headers=headers, json=payload)
    duplicate = http.post("/api/openlineage/events", headers=headers, json=payload)
    assert first.status_code == 200
    assert first.json()["inserted"] is True
    assert duplicate.json()["inserted"] is False
    assert first.json()["event_id"] == duplicate.json()["event_id"]


@pytest.mark.parametrize(
    ("field", "value"), [("eventType", "PAUSED"), ("eventTime", "2026-10-27T01:00:00")]
)
def test_openlineage_invalid_event_rejects_before_storage(
    db: Database, monkeypatch: pytest.MonkeyPatch, field: str, value: str
) -> None:
    """Nonstandard event kinds and naive timestamps cannot become standard run records."""
    monkeypatch.setenv("DATAKEEL_OPENLINEAGE_TOKEN", "fixture-ingestion-token")
    payload = {**JsonDocument.model_validate_json(FIXTURE.read_text()).root, field: value}
    response = client(db).post(
        "/api/openlineage/events",
        headers={"Authorization": "Bearer fixture-ingestion-token"},
        json=payload,
    )
    assert response.status_code == 422
    with db.session() as session:
        assert all_events(session) == []


def test_openlineage_wrong_bearer_cannot_append_even_when_ingestion_is_enabled(
    db: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An enabled endpoint still authenticates the supplied producer credential."""
    monkeypatch.setenv("DATAKEEL_OPENLINEAGE_TOKEN", "fixture-ingestion-token")
    response = client(db).post(
        "/api/openlineage/events",
        headers={"Authorization": "Bearer wrong-token"},
        json=JsonDocument.model_validate_json(FIXTURE.read_text()).root,
    )
    assert response.status_code == 403
    with db.session() as session:
        assert all_events(session) == []
