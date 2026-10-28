# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""HTTP suggestions expose weak evidence while preserving explicit mapping approval."""

import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from datakeel.api.app import create_app
from datakeel.catalog.service import import_catalog
from datakeel.core.catalog_models import CatalogImportRequest
from datakeel.core.standard_models import BusinessSynonyms, FieldStandard, StandardsContract
from datakeel.standards.loader import load_contract
from datakeel.standards.mapping import SUGGESTION_THRESHOLD
from datakeel.storage.database import Database


def _contract() -> StandardsContract:
    return StandardsContract(
        standards=(
            FieldStandard(
                code="reconciliation_amount",
                name_zh="对账金额",
                name_en="Reconciliation amount",
                description="Generated reconciliation total",
                data_type="number",
                status="active",
            ),
            FieldStandard(
                code="store_id",
                name_zh="门店编号",
                name_en="Store ID",
                description="Generated retail store identity",
                data_type="integer",
                status="active",
            ),
        ),
        synonyms=(BusinessSynonyms(canonical="store", alternatives=("shop", "outlet")),),
    )


def _configured_client(db: Database, directory: Path) -> tuple[TestClient, StandardsContract]:
    source = directory / "mapping-source.sqlite"
    with sqlite3.connect(source) as connection:
        connection.execute("CREATE TABLE activity(reconc TEXT, shop_id INTEGER)")
        connection.execute("INSERT INTO activity VALUES ('pending', 7)")
    import_catalog(
        db,
        CatalogImportRequest(
            source_id="generated", name="Generated", connection_url=f"sqlite:///{source}"
        ),
    )
    client = TestClient(create_app(db))
    contract = _contract()
    prepared = client.post(
        "/api/actions/import_standards/prepare",
        json={"contract": contract.model_dump(mode="json")},
    )
    assert prepared.status_code == 200
    plan = prepared.json()
    payload = {"plan_digest": plan["plan_digest"]}
    assert client.post(f"/api/actions/{plan['id']}/execute", json=payload).status_code == 403
    approved = client.post(f"/api/approvals/{plan['id']}", json={**payload, "approve": True})
    assert approved.status_code == 200
    assert client.post(f"/api/actions/{plan['id']}/execute", json=payload).status_code == 200
    return client, contract


def test_http_partial_candidates_serialize_confidence_without_persisting_decisions(
    db: Database, tmp_path: Path
) -> None:
    """Partial lexical and synonym evidence stays visible and read-only across HTTP."""
    client, _ = _configured_client(db, tmp_path)
    before_mappings = client.get("/api/standards/mappings").json()
    before_history = client.get("/api/standards/history").json()
    response = client.get("/api/standards/suggestions")
    assert response.status_code == 200
    suggestions = {item["column_id"]: item["candidates"] for item in response.json()}
    partial = suggestions["generated/main/activity/reconc"][0]
    assert partial["standard_code"] == "reconciliation_amount"
    assert partial["low_confidence"] is True
    assert partial["score"] < SUGGESTION_THRESHOLD
    assert any("Prefix:" in reason for reason in partial["reasons"])
    assert any("Low confidence:" in reason for reason in partial["reasons"])
    synonym = suggestions["generated/main/activity/shop_id"][0]
    assert synonym["standard_code"] == "store_id"
    assert synonym["low_confidence"] is False
    assert any("Synonym:" in reason for reason in synonym["reasons"])
    assert before_mappings == client.get("/api/standards/mappings").json() == []
    assert client.get("/api/standards/history").json() == before_history
    assert len(before_history["revisions"]) == 1


def test_http_contract_and_yaml_export_preserve_imported_business_synonyms(
    db: Database, tmp_path: Path
) -> None:
    """The approved contract retains synonym groups through both portable read formats."""
    client, expected = _configured_client(db, tmp_path)
    response = client.get("/api/standards/contract")
    assert response.status_code == 200
    assert response.json()["synonyms"] == [
        {"canonical": "store", "alternatives": ["shop", "outlet"]}
    ]
    assert StandardsContract.model_validate(response.json()) == expected
    exported = client.get("/api/standards/export")
    assert exported.status_code == 200
    path = tmp_path / "exported-standards.yaml"
    path.write_text(exported.text)
    assert load_contract(path) == expected
