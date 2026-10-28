# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Standards browsing, strict import plans, human decisions and read-only reports over HTTP."""

from pathlib import Path

from fastapi.testclient import TestClient

from datakeel.api.app import create_app
from datakeel.storage.database import Database
from tests.standards_support import install_standards


def test_standard_reads_search_filter_export_and_schema(db: Database, tmp_path: Path) -> None:
    """Public reads share an effective contract without returning source data."""
    install_standards(db, tmp_path)
    client = TestClient(create_app(db))
    assert len(client.get("/api/standards/fields").json()) == 4
    assert (
        client.get(
            "/api/standards/fields", params={"search": "客户编号", "status": "active"}
        ).json()[0]["code"]
        == "customer_id"
    )
    assert client.get("/api/standards/fields?status=deprecated").json() == []
    assert client.get("/api/standards/fields?status=invalid").status_code == 422
    assert client.get("/api/standards/code-lists?search=Active").json()[0]["code"] == "states"
    assert client.get("/api/standards/contract").json()["standards"]
    exported = client.get("/api/standards/export")
    assert exported.status_code == 200
    assert "name_zh:" in exported.text
    assert client.get("/api/standards/schema").json()["additionalProperties"] is False
    assert len(client.get("/api/standards/history").json()["revisions"]) == 1
    assert len(client.get("/api/standards/profiles").json()) == 5
    assert len(client.get("/api/standards/suggestions").json()) == 5
    assert client.get("/api/standards/mappings").json() == []
    assert client.get("/api/standards/checks").json() == []
    assert client.get("/api/standards/coverage").json()["overall"]["mapped_columns"] == 0
    report = client.get("/api/standards/report?table_id=generated/main/customers")
    assert report.status_code == 200
    assert "safe@example.org" not in report.text


def test_http_confirmation_requires_matching_human_decision(db: Database, tmp_path: Path) -> None:
    """Coverage changes only after an exact local approval and one execution."""
    install_standards(db, tmp_path)
    client = TestClient(create_app(db))
    plan = client.post(
        "/api/actions/confirm_standard_mapping/prepare",
        json={
            "mapping": {
                "column_id": "generated/main/customers/cust_id",
                "standard_code": "customer_id",
            }
        },
    ).json()
    payload = {"plan_digest": plan["plan_digest"]}
    assert client.post(f"/api/actions/{plan['id']}/execute", json=payload).status_code == 403
    assert client.get("/api/standards/mappings").json() == []
    assert (
        client.post(f"/api/approvals/{plan['id']}", json={**payload, "approve": True}).status_code
        == 200
    )
    assert client.post(f"/api/actions/{plan['id']}/execute", json=payload).status_code == 200
    assert client.get("/api/standards/checks").json()[0]["violations"]
    assert client.get("/api/standards/coverage").json()["overall"]["mapped_columns"] == 1
    assert (
        client.post(
            "/api/actions/import_standards/prepare", json={"contract": {"unexpected": True}}
        ).status_code
        == 422
    )
