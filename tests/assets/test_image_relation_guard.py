# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Image-derived graph facts resolve to their protected dataset like text-derived facts."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from datakeel.api.app import create_app
from datakeel.core.data_asset_models import AccessContext
from datakeel.core.errors import AuthorizationError
from datakeel.core.kg_queries import KGQuery
from datakeel.core.models import AssetRef, JsonDocument
from datakeel.ontology.tool_models import ToolCallContext
from datakeel.ontology.tooling import invoke_tool
from datakeel.storage.data_asset_access import require_access
from datakeel.storage.database import Database
from datakeel.storage.kg_queries import explain_relation, query_kg
from tests.assets.entry_helpers import grant, publish
from tests.kg.integration_helpers import execute_graph, install_adapter, pair_result
from tests.worker.image_helpers import (
    image_dataset,
    install_transcriber,
    prepare_image,
    transcript,
    use_profile,
)

READER = AccessContext(actor="local", entry="agent", scope="query")


def test_image_relation_when_dataset_protected_denies_every_explanation_entry(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Content-revision image anchors and versioned entities must not bypass the policy."""
    dataset = image_dataset(db, tmp_path)
    use_profile(monkeypatch)
    install_transcriber(monkeypatch, (transcript(),))
    install_adapter(monkeypatch, (pair_result(),))
    execute_graph(db, prepare_image(db, dataset))
    relation = query_kg(db, KGQuery(dataset_id=dataset.dataset_id)).relations[0].assertion
    assert {anchor.asset_ref.version for anchor in relation.anchors} != {dataset.version_id}
    asset = publish(db, AssetRef(asset_id=dataset.dataset_id))

    with pytest.raises(AuthorizationError):
        explain_relation(db, relation.id)
    outcome = invoke_tool(
        db, "explain_relation", JsonDocument({"assertion_id": relation.id}), ToolCallContext()
    )
    assert outcome.status == "FAILED"
    assert "apply for access" in (outcome.error or "")
    assert outcome.content.root == {}
    with TestClient(create_app(db), headers={"X-Datakeel-Actor": "local"}) as client:
        response = client.get(f"/api/kg/relations/{relation.id}")
        assert response.status_code == 403
        assert "Acme" not in response.text
        grant(db, asset, "valid", "query")
        assert client.get(f"/api/kg/relations/{relation.id}").status_code == 200


def test_entity_and_revision_refs_when_dataset_protected_resolve_to_dataset(
    db: Database, tmp_path: Path
) -> None:
    """A graph entity version and an unknown content revision both map to the owning dataset."""
    dataset = image_dataset(db, tmp_path)
    publish(db, AssetRef(asset_id=dataset.dataset_id))
    for ref in (
        AssetRef(asset_type="kg_entity", asset_id="kg-generated", version=dataset.version_id),
        AssetRef(asset_type="file", asset_id=dataset.files[0].id, version="f" * 64),
    ):
        with pytest.raises(AuthorizationError):
            require_access(db, (ref,), READER, record=False)
    unrelated = AssetRef(asset_type="kg_entity", asset_id="kg-generated", version="missing")
    assert require_access(db, (unrelated,), READER, record=False) == ()
