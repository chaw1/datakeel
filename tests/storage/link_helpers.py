# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Create small isolated graph observations with deterministic source spans."""

import hashlib

from datakeel.core.catalog_models import CatalogObject, CatalogSnapshot
from datakeel.core.evidence_models import ExtractorRef
from datakeel.core.kg_contracts import ExtractedEntity, ExtractedRelation
from datakeel.core.kg_models import RawExtraction
from datakeel.core.kg_product import KGSource
from datakeel.core.models import AssetRef
from datakeel.kg.assembly import assemble_extraction
from datakeel.kg.loader import get_schema
from datakeel.storage.database import Database
from tests.kg.helpers import seed_graph


def table_snapshot(name: str = "sales", scope: str = "crm") -> CatalogSnapshot:
    """Create a catalog revision whose identity remains stable across name changes."""
    return CatalogSnapshot(
        scope=scope,
        objects=(
            CatalogObject(
                asset_ref=AssetRef(asset_type="table", asset_id=f"{scope}/main/sales"),
                name=name,
                schema_name="main",
            ),
        ),
    )


def seed_link_graph(
    db: Database,
    name: str = "sales table",
    version: str = "v1",
    dataset: str = "dataset",
    entity_type: str = "dataset",
) -> None:
    """Record a person owning a named dataset or metric in one immutable document."""
    text = f"Jordan owns {name}."
    source = KGSource(
        dataset_id=dataset,
        dataset_version_id=version,
        file=AssetRef(
            asset_type="file", asset_id=f"doc-{dataset}-{version}-{name}", version=version
        ),
        text=text,
        content_revision=hashlib.sha256(text.encode()).hexdigest(),
        extractor=ExtractorRef(id="evidence.kg", version="fixture"),
    )
    output = RawExtraction(
        entities=(
            ExtractedEntity(name="Jordan", type="person"),
            ExtractedEntity(name=name, type=entity_type),
        ),
        relations=(ExtractedRelation(head="Jordan", relation="owns", tail=name, evidence=text),),
    )
    seed_graph(db, assemble_extraction(output, get_schema(), source), source)
