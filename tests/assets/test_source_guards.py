# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Frozen source and evidence viewers enforce the same native asset permissions."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from datakeel.api.app import create_app
from datakeel.core.data_asset_models import AssetUsageQuery
from datakeel.core.errors import AuthorizationError
from datakeel.core.kg_queries import KGQuery
from datakeel.core.models import AssetRef, BoundaryModel, JsonDocument
from datakeel.evidence.query_models import EvidenceQuery
from datakeel.ontology.tool_models import ToolCallContext
from datakeel.ontology.tooling import invoke_tool
from datakeel.storage.data_asset_access import list_usage
from datakeel.storage.database import Database
from datakeel.storage.evidence_queries import get_evidence, query_evidence
from datakeel.storage.kg_image_sources import image_bytes
from datakeel.storage.kg_queries import get_source_text, query_kg
from datakeel.storage.kg_store import get_job
from tests.assets.entry_helpers import grant, publish
from tests.evidence.interface_fixtures import seed_query_evidence
from tests.kg.integration_helpers import (
    execute_graph,
    install_adapter,
    pair_result,
    prepare_graph,
    text_dataset,
)
from tests.worker.image_helpers import (
    image_dataset,
    install_transcriber,
    prepare_image,
    transcript,
    use_profile,
)


class SourceFixture(BoundaryModel):
    """Retain the generated graph coordinates used by the frozen source endpoints."""

    dataset_id: str
    file_id: str
    version_id: str
    extraction_id: str
    relation_id: str


@pytest.fixture
def source(db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SourceFixture:
    """Run an injected offline extractor before publishing a protected policy."""
    dataset = text_dataset(db, tmp_path, ("Acme uses Widget.",))
    install_adapter(monkeypatch, (pair_result(),))
    run = execute_graph(db, prepare_graph(db, dataset))
    result = query_kg(db, KGQuery(dataset_id=dataset.dataset_id))
    return SourceFixture(
        dataset_id=dataset.dataset_id,
        file_id=dataset.files[0].id,
        version_id=dataset.version_id,
        extraction_id=run.id,
        relation_id=result.relations[0].assertion.id,
    )


@pytest.mark.parametrize("viewer", ["source", "query", "graph", "relation"])
def test_graph_viewers_when_protected_require_query_scope(
    db: Database, source: SourceFixture, viewer: str
) -> None:
    """Exact source, graph, candidates and explanation endpoints deny and then allow one grant."""
    asset = publish(db, AssetRef(asset_id=source.dataset_id))
    with TestClient(create_app(db), headers={"X-Datakeel-Actor": "local"}) as client:

        def read() -> int:
            if viewer in {"query", "graph"}:
                return client.post(
                    f"/api/kg/{viewer}", json={"dataset_id": source.dataset_id}
                ).status_code
            if viewer == "relation":
                return client.get(f"/api/kg/relations/{source.relation_id}").status_code
            return client.get(
                f"/api/kg/sources/{source.file_id}",
                params={"version_id": source.version_id, "extraction_id": source.extraction_id},
            ).status_code

        assert read() == 403
        grant(db, asset, "valid", "query")
        assert read() == 200
    assert len(list_usage(db, AssetUsageQuery(asset_id=asset.id))) == 1
    with pytest.raises(AuthorizationError):
        get_source_text(db, source.file_id, source.version_id, source.extraction_id)


def test_image_pixels_when_authorized_use_calling_operator_and_download_scope(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The image response passes its actor through to the actual underlying download guard."""
    dataset = image_dataset(db, tmp_path)
    use_profile(monkeypatch)
    install_transcriber(monkeypatch, (transcript(),))
    install_adapter(monkeypatch, (pair_result(),))
    run = execute_graph(db, prepare_image(db, dataset))
    document = get_job(db, run.id).documents[0]
    assert document.image is not None
    image = document.image.asset_ref
    assert image.version is not None
    asset = publish(db, AssetRef(asset_id=dataset.dataset_id))
    with pytest.raises(AuthorizationError):
        image_bytes(db, image.asset_id, image.version, run.id)
    with TestClient(create_app(db), headers={"X-Datakeel-Actor": "local"}) as client:
        url = f"/api/kg/images/{image.asset_id}"
        params = {"version_id": image.version, "extraction_id": run.id}
        assert client.get(url, params=params).status_code == 403
        grant(db, asset, "valid", "query")
        assert client.get(url, params=params).status_code == 403
        grant(db, asset, "valid", "download")
        response = client.get(url, params=params)
        assert response.status_code == 200
        assert response.content.startswith(b"\x89PNG")
    assert len(list_usage(db, AssetUsageQuery(asset_id=asset.id))) == 1


def test_evidence_viewers_when_protected_hide_captions_and_assertions(
    db: Database, tmp_path: Path
) -> None:
    """Both public evidence pages and their underlying service deny unauthorized source values."""
    dataset = seed_query_evidence(db, tmp_path / "samples")
    sample = query_evidence(db, EvidenceQuery(dataset_id=dataset)).items[0]
    asset = publish(db, AssetRef(asset_id=dataset))
    with pytest.raises(AuthorizationError):
        get_evidence(db, sample.asset_ref.asset_id)
    with TestClient(create_app(db), headers={"X-Datakeel-Actor": "local"}) as client:
        assert client.post("/api/evidence/query", json={"dataset_id": dataset}).status_code == 403
        assert client.get(f"/api/evidence/assets/{sample.asset_ref.asset_id}").status_code == 403
        grant(db, asset, "valid", "query")
        assert client.post("/api/evidence/query", json={"dataset_id": dataset}).status_code == 200
        assert client.get(f"/api/evidence/assets/{sample.asset_ref.asset_id}").status_code == 200
    assert len(list_usage(db, AssetUsageQuery(asset_id=asset.id))) == 2


def test_graph_tools_when_authorized_append_once_per_asset(
    db: Database, source: SourceFixture
) -> None:
    """Nested graph services preserve tool actors and leave each usage to the outer boundary."""
    asset = publish(db, AssetRef(asset_id=source.dataset_id))
    grant(db, asset, "valid", "query")
    for tool, params in (
        ("query_kg", JsonDocument({"dataset_id": source.dataset_id})),
        ("explain_relation", JsonDocument({"assertion_id": source.relation_id})),
    ):
        result = invoke_tool(db, tool, params, ToolCallContext(actor="local"))
        assert result.status == "SUCCEEDED", result.error
    records = list_usage(db, AssetUsageQuery(asset_id=asset.id))
    assert len(records) == 2
    assert all(item.entry == "agent" for item in records)
