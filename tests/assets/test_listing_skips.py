# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Listings and exports skip protected entries by ID instead of failing the whole read."""

import asyncio
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from fastmcp import Client
from pydantic import TypeAdapter

from datakeel.api.app import create_app
from datakeel.core.data_asset_models import AccessEntry, DataAsset, SkippedEntries
from datakeel.core.metric_models import MetricCard
from datakeel.core.models import AssetRef, BoundaryModel, JsonDocument, LineageEvent
from datakeel.lineage.models import GraphView
from datakeel.mcp import create_server
from datakeel.ontology.models import FunctionResult
from datakeel.ontology.tool_models import ToolCallContext, ToolOutcome
from datakeel.ontology.tooling import invoke_tool
from datakeel.storage.database import Database
from datakeel.storage.dataset_service import import_paths
from datakeel.storage.lineage_service import record_event
from datakeel.storage.views import DatasetView
from tests.assets.entry_helpers import EntryResources, grant, publish, seed_resources

PROTECTED_NAME = "Generated controlled asset"
DATASETS = TypeAdapter(list[DatasetView])


class MetricItems(BoundaryModel):
    """The paginated metric listing returned by the catalog tool."""

    items: list[MetricCard]
    total: int
    offset: int
    limit: int


class Scene:
    """A protected dataset and metric beside a public dataset linked by one lineage event."""

    def __init__(self, db: Database, tmp_path: Path) -> None:
        """Publish the policies and record the derivation that links both datasets."""
        self.resources: EntryResources = seed_resources(db, tmp_path)
        public = tmp_path / "public.txt"
        public.write_text("Generated public sample.")
        self.public_id = import_paths(db, "Generated public dataset", [public]).id
        self.dataset_asset: DataAsset = publish(
            db, AssetRef(asset_id=self.resources.dataset_id), "restricted"
        )
        self.metric_asset: DataAsset = publish(
            db, AssetRef(asset_type="metric", asset_id="retail_revenue"), "request"
        )
        self.event = LineageEvent(
            idempotency_key="generated-protected-derivation",
            operator="fixture.derive",
            inputs=[AssetRef(asset_id=self.public_id)],
            outputs=[AssetRef(asset_id=self.resources.dataset_id)],
        )
        assert record_event(db, self.event)


@pytest.fixture
def scene(db: Database, tmp_path: Path) -> Scene:
    """Seed the protected and public resources once per test."""
    return Scene(db, tmp_path)


def _tool(db: Database, entry: AccessEntry, name: str, arguments: dict[str, object]) -> ToolOutcome:
    document = JsonDocument.model_validate(arguments)
    if entry == "agent":
        return invoke_tool(db, name, document, ToolCallContext(session_id=f"skip-{name}"))

    async def call() -> ToolOutcome:
        async with Client(create_server(db), mode="legacy") as client:
            response = await client.call_tool(name, document.root, raise_on_error=False)
            return ToolOutcome.model_validate(response.structured_content)

    return asyncio.run(call())


def _result(outcome: ToolOutcome) -> tuple[FunctionResult, SkippedEntries]:
    assert outcome.status == "SUCCEEDED", outcome.error
    result = FunctionResult.model_validate(outcome.content.root)
    assert result.skipped is not None
    return result, result.skipped


@pytest.mark.parametrize("entry", ["agent", "mcp"])
def test_list_tools_skip_protected_entries_and_name_them_by_id(
    db: Database, scene: Scene, entry: AccessEntry
) -> None:
    """Protected datasets and metrics are left out with count, IDs, assets and a reason."""
    datasets = _tool(db, entry, "list_datasets", {})
    result, skipped = _result(datasets)
    listed = {item.id for item in DATASETS.validate_python(result.data)}
    assert scene.public_id in listed
    assert scene.resources.dataset_id not in listed
    assert skipped.count == 1
    assert skipped.ids == [scene.resources.dataset_id]
    assert skipped.assets == [scene.dataset_asset.id]
    assert "apply for access" in skipped.reason
    assert PROTECTED_NAME not in datasets.content.model_dump_json()
    result, skipped = _result(_tool(db, entry, "list_metrics", {"limit": 100}))
    page = MetricItems.model_validate(result.data)
    ids = {item.definition.id for item in page.items}
    assert "retail_revenue" not in ids
    assert ids
    assert skipped.ids == ["retail_revenue"]
    assert page.total == len(ids)


def test_lineage_tool_drops_protected_nodes_events_and_edges(db: Database, scene: Scene) -> None:
    """A readable root keeps its graph minus the protected node and the event touching it."""
    outcome = _tool(db, "agent", "get_lineage", {"asset_id": scene.public_id})
    result, skipped = _result(outcome)
    graph = GraphView.model_validate(result.data)
    rendered = graph.model_dump_json()
    assert scene.public_id in {node.asset_id for node in graph.nodes}
    assert scene.resources.dataset_id not in rendered
    assert scene.event.event_id not in rendered
    assert graph.edges
    assert scene.event.event_id in skipped.ids
    assert scene.dataset_asset.id in skipped.assets
    assert PROTECTED_NAME not in outcome.content.model_dump_json()
    protected = _tool(db, "agent", "get_lineage", {"asset_id": scene.resources.dataset_id})
    assert protected.status == "FAILED"
    assert "apply for access" in (protected.error or "")


def test_grant_restores_entries_and_omits_the_skip_report(db: Database, scene: Scene) -> None:
    """With a valid grant nothing is skipped and existing result shapes stay unchanged."""
    grant(db, scene.dataset_asset, "valid", "query")
    outcome = _tool(db, "agent", "list_datasets", {})
    assert outcome.status == "SUCCEEDED", outcome.error
    assert "skipped" not in outcome.content.model_dump()
    result = FunctionResult.model_validate(outcome.content.root)
    listed = {item.id for item in DATASETS.validate_python(result.data)}
    assert scene.resources.dataset_id in listed


def test_openlineage_export_skips_protected_events_and_reports_them_in_headers(
    db: Database, scene: Scene
) -> None:
    """Full and component exports keep RunEvent arrays; explicit protected targets stay denied."""
    with TestClient(create_app(db), raise_server_exceptions=False) as client:
        full = client.get("/api/export", params={"format": "openlineage"})
        component = client.get(
            "/api/export", params={"format": "openlineage", "dataset_id": scene.public_id}
        )
        denied = client.get(
            "/api/export",
            params={"format": "openlineage", "dataset_id": scene.resources.dataset_id},
        )
    for response in (full, component):
        assert response.status_code == 200, response.text
        assert isinstance(response.json(), list)
        assert scene.event.event_id not in response.text
        assert scene.resources.dataset_id not in response.text
        skipped_ids = response.headers["X-Datakeel-Skipped-Ids"].split(",")
        assert scene.event.event_id in skipped_ids
        assert response.headers["X-Datakeel-Skipped-Count"] == str(len(skipped_ids))
        assert scene.dataset_asset.id in response.headers["X-Datakeel-Skipped-Assets"]
        assert "apply for access" in response.headers["X-Datakeel-Skipped-Reason"]
    assert any(scene.public_id in json.dumps(event) for event in full.json())
    assert denied.status_code == 403
    assert "apply for access" in denied.text
