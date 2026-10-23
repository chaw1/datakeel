# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Immutable graph responses retain the authoritative lineage observations."""

import pytest
from pydantic import ValidationError

from datakeel.core.catalog_models import CatalogLink, CatalogObject, CatalogSnapshot
from datakeel.core.models import AssetRef, LineageEvent
from datakeel.lineage.models import GraphOverlay
from datakeel.lineage.service import graph


def test_graph_unknown_asset_returns_empty_projection() -> None:
    """Verify graph unknown asset returns empty projection."""
    result = graph([], "missing")
    assert result.nodes == []
    assert result.edges == []


def test_graph_depth_zero_retains_only_selected_asset() -> None:
    """Verify graph depth zero retains only selected asset."""
    event = LineageEvent(
        idempotency_key="depth",
        operator="fixture.transform",
        inputs=[AssetRef(asset_id="source")],
        outputs=[AssetRef(asset_id="target")],
    )
    result = graph([event], "source", depth=0)
    assert [node.asset_id for node in result.nodes] == ["source"]
    assert result.edges == []
    with pytest.raises(ValidationError, match="frozen"):
        result.nodes = []


@pytest.mark.parametrize("state", ["FAILED", "FAIL"])
def test_failed_observation_without_outputs_remains_in_selected_graph(state: str) -> None:
    """Verify failed observation without outputs remains in selected graph."""
    event = LineageEvent(
        idempotency_key="failed-observation",
        operator="fixture.failure",
        run_state=state,
        inputs=[AssetRef(asset_id="source")],
        outputs=[],
    )
    selected = graph([event], "source")
    assert selected.events == [event]
    assert selected.edges == []
    assert graph([event], "unrelated").events == []


def test_global_graph_retains_unattached_failure_evidence() -> None:
    """Verify global graph retains unattached failure evidence."""
    event = LineageEvent(idempotency_key="unattached", operator="fixture.failure", run_state="FAIL")
    assert graph([event]).events == [event]


def test_catalog_graph_when_columns_share_names_qualifies_tables_and_preserves_semantic_names() -> (
    None
):
    """Link references cannot overwrite human catalog names with their older display names."""
    objects = [
        CatalogObject(asset_ref=AssetRef(asset_type=kind, asset_id=identity), name=name)
        for kind, identity, name in (
            ("metric", "retail_revenue", "零售额"),
            ("dimension", "retail_region", "零售区域"),
            ("term", "term/零售额", "零售额"),
            ("table", "generated/main/orders", "orders"),
            ("table", "generated/main/sales", "sales"),
        )
    ]
    columns = [
        CatalogObject(
            asset_ref=AssetRef(
                asset_type="column", asset_id=f"generated/main/{table}/date", display_name="date"
            ),
            name="date",
            table_id=f"generated/main/{table}",
        )
        for table in ("orders", "sales", "unresolved")
    ]
    event = LineageEvent(event_id="catalog-event", idempotency_key="names", operator="import")
    snapshot = CatalogSnapshot(
        scope="generated",
        objects=(*objects, *columns),
        links=(
            CatalogLink(
                source=objects[0].asset_ref,
                target=columns[0].asset_ref,
                kind="measures",
                producer_event_id=event.event_id,
            ),
        ),
    )
    result = graph([event], assertions=GraphOverlay(catalog=snapshot))
    names = {node.asset_id: node.display_name for node in result.nodes}
    assert names["retail_revenue"] == "零售额"
    assert names["retail_region"] == "零售区域"
    assert names["term/零售额"] == "零售额"
    assert names["generated/main/orders/date"] == "orders.date"
    assert names["generated/main/sales/date"] == "sales.date"
    assert names["generated/main/unresolved/date"] == "unresolved.date"
    assert snapshot.links[0].target.display_name == "date"
