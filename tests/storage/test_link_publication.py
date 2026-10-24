# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Run linking against real offline publication, semantic updates and evidence replay."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from datakeel.core.evidence_models import AssertionDecisionRequest
from datakeel.harness.enterprise_cases import seed_enterprise_case
from datakeel.harness.enterprise_kg import (
    extract_enterprise_documents,
    import_enterprise_documents,
    seed_enterprise_kg,
)
from datakeel.harness.enterprise_reviews import review_enterprise_kg
from datakeel.metrics.loader import load_layer
from datakeel.storage.evidence_decisions import decide_assertions
from datakeel.storage.evidence_projection import rebuild_evidence
from datakeel.storage.link_queries import list_links, read_link_context
from datakeel.storage.link_store import relink
from datakeel.storage.metric_store import install_layer
from tests.storage.link_helpers import seed_link_graph

if TYPE_CHECKING:
    from datakeel.storage.database import Database


def test_enterprise_links_reextract_review_and_rebuild_without_p8_regression(
    db: Database, tmp_path: Path
) -> None:
    """Production replay links aliases safely and keeps both kinds of human review."""
    fixture = seed_enterprise_kg(db, tmp_path)
    links = list_links(db, fixture.dataset_id)
    assert {link.entity.name for link in links if link.target.name == "sales"} == {
        "sales",
        "sales table",
    }
    assert not any(
        link.entity.name in {"erp_raw_shipments", "inventory_snapshot"} for link in links
    )
    turnover = [link for link in links if link.entity.name == "营业额"]
    assert {link.target.name for link in turnover} == {"销售额", "零售额"}
    assert {link.match_kind for link in turnover} == {"ambiguous"}
    assert all(link.assertion.status == "candidate" for link in turnover)
    assert not any(item.predicate == "kg.same_as" for item in read_link_context(db).assertions)
    review_enterprise_kg(db, fixture)
    reviewed = {
        link.target.name: link.assertion.status
        for link in list_links(db)
        if link.entity.name == "营业额"
    }
    assert reviewed == {"销售额": "accepted", "零售额": "rejected"}
    assert relink(db).created == 0
    before = read_link_context(db)
    assert rebuild_evidence(db).matches
    assert read_link_context(db) == before


def test_production_graph_before_catalog_links_on_later_import(
    db: Database, tmp_path: Path
) -> None:
    """Publishing graph data first still creates table and metric links as metadata arrives."""
    fixture = import_enterprise_documents(db, tmp_path / "documents")
    extract_enterprise_documents(db, fixture)
    assert list_links(db) == ()
    seed_enterprise_case(db, tmp_path)
    links = list_links(db)
    assert any(link.target.name == "shipments" for link in links)
    assert any(link.target.name == "出货额" for link in links)
    assert relink(db).created == 0


def test_semantic_install_and_revision_refresh_accepted_metric_links(db: Database) -> None:
    """Initial installation and a versioned semantic update trigger the same linking path."""
    seed_link_graph(db, name="出货额", entity_type="metric")
    layer = load_layer(Path("contracts/semantic-layer"))
    install_layer(db, layer)
    original = list_links(db)[0]
    decide_assertions(
        db,
        AssertionDecisionRequest(
            assertion_ids=(original.assertion.id,),
            status="accepted",
            actor="reviewer",
            idempotency_key="accept-metric",
        ),
    )
    changed = layer.model_copy(
        update={
            "metrics": [
                metric.model_copy(update={"description": "New registered description"})
                if metric.id == "shipment_amount"
                else metric
                for metric in layer.metrics
            ]
        }
    )
    install_layer(db, changed)
    current = list_links(db)[0]
    assert current.target.asset_ref.version == "2"
    assert current.assertion.id != original.assertion.id
    assert current.assertion.status == "accepted"
