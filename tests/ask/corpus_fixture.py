# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Generate isolated metadata and fake query results for corpus route evaluation."""

from pathlib import Path

import pytest

from datakeel.ask import knowledge_service
from datakeel.ask import service as ask_service
from datakeel.core.catalog_models import (
    CatalogObject,
    CatalogSnapshot,
    ColumnProperties,
    SourceProperties,
    TableProperties,
)
from datakeel.core.kg_product import KGEntity
from datakeel.core.link_models import LinkContext
from datakeel.core.metric_models import (
    CompiledQuery,
    DimensionDefinition,
    Measure,
    MetricDefinition,
    MetricTime,
    QueryResult,
    SemanticLayer,
)
from datakeel.core.models import AssetRef, JsonDocument
from datakeel.metrics.projection import build_snapshot
from datakeel.storage.catalog_store import publish_snapshot
from datakeel.storage.database import Database
from tests.ask.corpus_models import CorpusCatalog, CorpusFixture, CorpusSubject

_TABLE = "corpus/main/corpus_values"


def _data_objects() -> tuple[CatalogObject, ...]:
    columns = tuple(
        CatalogObject(
            asset_ref=AssetRef(asset_type="column", asset_id=f"{_TABLE}/{name}"),
            name=name,
            source_id="corpus",
            table_id=_TABLE,
            properties=JsonDocument(
                ColumnProperties(data_type="TEXT", ordinal=index).model_dump(mode="json")
            ),
        )
        for index, name in enumerate(("amount", "day", "owner", "channel", "region", "supplier"))
    )
    return (
        CatalogObject(
            asset_ref=AssetRef(asset_type="source", asset_id="corpus"),
            name="Corpus fixture",
            properties=JsonDocument(
                SourceProperties(dialect="sqlite", connection_url="sqlite:///:memory:").model_dump(
                    mode="json"
                )
            ),
        ),
        CatalogObject(
            asset_ref=AssetRef(asset_type="table", asset_id=_TABLE),
            name="corpus_values",
            source_id="corpus",
            schema_name="main",
        ),
        *columns,
    )


def _table_object(subject: CorpusSubject) -> CatalogObject:
    return CatalogObject(
        asset_ref=AssetRef(asset_type="table", asset_id=subject.asset_id),
        name=subject.name,
        source_id="corpus",
        schema_name="main",
        properties=JsonDocument(
            TableProperties(is_view=subject.kind == "view").model_dump(mode="json")
        ),
    )


def _layer(subjects: tuple[CorpusSubject, ...]) -> SemanticLayer:
    dimensions = [
        DimensionDefinition(id=identity, name=name, synonyms=aliases, column=f"{_TABLE}/{column}")
        for identity, name, aliases, column in (
            ("owner", "负责人", ["维护负责人", "owner"], "owner"),
            (
                "channel",
                "来源渠道",
                ["数据来源渠道", "下游渠道", "source channel", "downstream channels"],
                "channel",
            ),
            ("region", "区域", ["region"], "region"),
            ("supplier", "上游供应商", ["upstream supplier"], "supplier"),
        )
    ]
    return SemanticLayer(
        metrics=[
            MetricDefinition(
                id=item.id,
                name=item.name,
                synonyms=list(item.aliases),
                description="Generated fixture for deterministic route evaluation.",
                owner="Corpus Custodian",
                measure=Measure(table=_TABLE, column=f"{_TABLE}/amount", aggregation="sum"),
                time=MetricTime(column=f"{_TABLE}/day"),
                dimensions=[item.id for item in dimensions],
            )
            for item in subjects
            if item.kind == "metric"
        ],
        dimensions=dimensions,
    )


def build_corpus_fixture() -> CorpusFixture:
    """Build the complete known catalog without reading either question partition."""
    path = Path(__file__).with_name("knowledge_corpus_catalog.json")
    catalog = CorpusCatalog.model_validate_json(path.read_text(encoding="utf-8"))
    tables = tuple(
        _table_object(item) for item in catalog.subjects if item.kind in {"table", "view"}
    )
    roles = tuple(
        CatalogObject(asset_ref=AssetRef(asset_type="owner", asset_id=item.id), name=item.name)
        for item in catalog.subjects
        if item.kind == "role"
    )
    data = CatalogSnapshot(scope="corpus-data", objects=(*_data_objects(), *tables, *roles))
    semantic = build_snapshot(_layer(catalog.subjects), data)
    snapshot = CatalogSnapshot(
        scope="corpus", objects=(*data.objects, *semantic.objects), links=semantic.links
    )
    entities = tuple(
        KGEntity(
            asset_ref=AssetRef(asset_type="kg_entity", asset_id=item.id, version="1"),
            name=item.name,
            type="person" if item.kind == "person" else "organization",
        )
        for item in catalog.subjects
        if item.kind in {"person", "team"}
    )
    return CorpusFixture(catalog=catalog, snapshot=snapshot, graph=LinkContext(entities=entities))


def patch_corpus_sources(
    db: Database, monkeypatch: pytest.MonkeyPatch, fixture: CorpusFixture
) -> None:
    """Register real metadata while replacing document and query I/O boundaries."""
    publish_snapshot(db, fixture.snapshot)

    def read_graph(_db: Database) -> LinkContext:
        return fixture.graph

    def execute_fixture(_connection: str, _query: CompiledQuery) -> QueryResult:
        return QueryResult(columns=["value"], rows=[[42]])

    monkeypatch.setattr(ask_service, "execute_query", execute_fixture)
    monkeypatch.setattr(knowledge_service, "read_link_context", read_graph)
    monkeypatch.setattr(ask_service, "read_link_context", read_graph, raising=False)
