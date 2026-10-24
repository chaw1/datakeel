# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Reject context-sentence matches outside the entity's exact mention coordinates."""

import hashlib

from datakeel.core.catalog_models import CatalogObject, CatalogSnapshot
from datakeel.core.evidence_models import ExtractorRef
from datakeel.core.kg_contracts import ExtractedEntity
from datakeel.core.kg_execution import KGDocument
from datakeel.core.kg_models import RawExtraction
from datakeel.core.kg_product import KGSource
from datakeel.core.link_models import LinkGraph
from datakeel.core.models import AssetRef
from datakeel.kg.assembly import assemble_extraction
from datakeel.kg.loader import get_schema
from datakeel.storage.link_drafts import link_drafts
from tests.kg.helpers import assertions_for


def _graph() -> LinkGraph:
    text = "inventory_snapshot is generated daily from the inventory table."
    source = KGSource(
        dataset_id="fixture",
        dataset_version_id="version",
        file=AssetRef(asset_type="file", asset_id="source", version="version"),
        text=text,
        content_revision=hashlib.sha256(text.encode()).hexdigest(),
        extractor=ExtractorRef(id="evidence.kg", version="fixture"),
    )
    schema = get_schema()
    schema = schema.model_copy(
        update={
            "entity_types": tuple(
                entity.model_copy(update={"aliases": {"Daily export": ("inventory_snapshot",)}})
                if entity.name == "dataset"
                else entity
                for entity in schema.entity_types
            )
        }
    )
    product = assemble_extraction(
        RawExtraction(entities=(ExtractedEntity(name="Daily export", type="dataset"),)),
        schema,
        source,
    )
    return LinkGraph(
        dataset_id="fixture",
        version_id="version",
        entities=product.entities,
        assertions=assertions_for(product),
        documents=(
            KGDocument(
                asset_ref=source.file,
                filename="source.txt",
                text=text,
                content_revision=source.content_revision,
                blocks=(),
            ),
        ),
    )


def test_only_mention_span_contributes_names_even_when_sentence_mentions_another_table() -> None:
    """An alias covering inventory_snapshot must never borrow inventory from its sentence."""
    graph = _graph()
    catalog = CatalogSnapshot(
        scope="fixture",
        objects=(
            CatalogObject(
                asset_ref=AssetRef(asset_type="table", asset_id="local/main/inventory"),
                name="inventory",
            ),
        ),
    )
    assert link_drafts((graph,), catalog, ()) == ()
    snapshot = catalog.objects[0].model_copy(
        update={
            "name": "inventory_snapshot",
            "asset_ref": AssetRef(asset_type="table", asset_id="local/main/inventory_snapshot"),
        }
    )
    actual = link_drafts((graph,), catalog.model_copy(update={"objects": (snapshot,)}), ())
    assert len(actual) == 1
    assert isinstance(actual[0].object, AssetRef)
    assert actual[0].object.asset_id == "local/main/inventory_snapshot"
    assert link_drafts((graph.model_copy(update={"assertions": ()}),), catalog, ()) == ()
