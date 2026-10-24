# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Create small synthetic graph claims independently from the enterprise recording."""

from datakeel.core.catalog_models import CatalogObject
from datakeel.core.evidence_models import Assertion, EvidenceAnchor, ExtractorRef, TextSpan
from datakeel.core.kg_product import KGEntity
from datakeel.core.kg_queries import KGSourceText
from datakeel.core.kg_registry import register_kg_schema
from datakeel.core.knowledge_models import KnowledgeSubject
from datakeel.core.link_models import EntityLink, LinkContext
from datakeel.core.models import AssetRef
from datakeel.kg.loader import get_schema

SOURCE = KGSourceText(
    asset_ref=AssetRef(asset_type="file", asset_id="document", version="version"),
    filename="synthetic-notes.txt",
    text="Revenue is computed from orders. Morgan owns Revenue.",
)
ANCHOR = EvidenceAnchor(
    asset_ref=SOURCE.asset_ref, content_revision="a" * 64, selector=TextSpan(start=0, end=32)
)


def entity(identity: str, name: str, kind: str) -> KGEntity:
    """Create a versioned graph identity without depending on extraction heuristics."""
    return KGEntity(
        asset_ref=AssetRef(asset_type="kg_entity", asset_id=identity, version="version"),
        name=name,
        type=kind,
    )


def assertion(identity: str, head: AssetRef, predicate: str, tail: AssetRef) -> Assertion:
    """Register standard relation semantics and create one source-backed candidate."""
    register_kg_schema(get_schema())
    return Assertion(
        id=identity,
        subject=head,
        predicate=predicate,
        object=tail,
        anchors=(ANCHOR,),
        extractor=ExtractorRef(id="fixture", version="1"),
        run_id="run",
        producer_event_id="event",
        verification="verified",
    )


def claim_context() -> tuple[KnowledgeSubject, LinkContext]:
    """Provide owner and upstream claims with independent unique asset associations."""
    metric, table, person = (
        entity("metric-entity", "Revenue", "metric"),
        entity("table-entity", "orders", "dataset"),
        entity("person-entity", "Morgan", "person"),
    )
    metric_asset = CatalogObject(
        asset_ref=AssetRef(asset_type="metric", asset_id="revenue", version="1"), name="Revenue"
    )
    table_asset = CatalogObject(
        asset_ref=AssetRef(asset_type="table", asset_id="source/main/orders", version="1"),
        name="orders",
    )
    links = tuple(
        EntityLink(
            assertion=assertion(
                f"link-{item.asset_ref.asset_id}", item.asset_ref, "link.maps_to", target.asset_ref
            ),
            entity=item,
            target=target,
            match_kind="unique",
            basis=("exact name",),
        )
        for item, target in ((metric, metric_asset), (table, table_asset))
    )
    return KnowledgeSubject(
        asset_ref=metric_asset.asset_ref, name="Revenue", kind="metric"
    ), LinkContext(
        entities=(metric, table, person),
        links=links,
        assertions=(
            assertion("upstream", metric.asset_ref, "kg.computed_from", table.asset_ref),
            assertion("ownership", person.asset_ref, "kg.owns", metric.asset_ref),
        ),
    )


def source_reader(_anchor: EvidenceAnchor) -> KGSourceText:
    """Return frozen source text for pure claim-selection unit tests."""
    return SOURCE
