# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Convert semantic definitions to typed, replayable catalog objects and edges."""

from datakeel.core.catalog_models import CatalogLink, CatalogObject, CatalogSnapshot
from datakeel.core.metric_models import (
    DimensionDefinition,
    MetricCard,
    MetricDefinition,
    OwnerDefinition,
    SemanticLayer,
    TermDefinition,
)
from datakeel.core.models import AssetRef, JsonDocument
from datakeel.metrics.loader import validate_unique
from datakeel.metrics.resolution import resolve_metric

SEMANTIC_SCOPE = "semantic-layer"


def metric_cards(snapshot: CatalogSnapshot) -> list[MetricCard]:
    """Decode versioned metric properties from the latest metadata projection."""
    return [
        MetricCard.model_validate(item.properties.root)
        for item in snapshot.objects
        if item.asset_ref.asset_type == "metric"
    ]


def semantic_layer(snapshot: CatalogSnapshot) -> SemanticLayer:
    """Decode all semantic definitions from a typed catalog snapshot."""
    return SemanticLayer(
        metrics=[item.definition for item in metric_cards(snapshot)],
        dimensions=[
            DimensionDefinition.model_validate(item.properties.root)
            for item in snapshot.objects
            if item.asset_ref.asset_type == "dimension"
        ],
        terms=[
            TermDefinition.model_validate(item.properties.root)
            for item in snapshot.objects
            if item.asset_ref.asset_type == "term"
        ],
        owners=[
            OwnerDefinition(name=item.name, english_name=item.english_name)
            for item in snapshot.objects
            if item.asset_ref.asset_type == "owner"
            and (item.properties.root or item.english_name is not None)
        ],
    )


def resolved_metric_cards(snapshot: CatalogSnapshot) -> list[MetricCard]:
    """Revalidate current dependencies without changing stored semantic revisions or history."""
    layer = semantic_layer(snapshot)
    assets = [item.asset_ref for item in snapshot.objects]
    return [_metric_card(metric, layer, assets) for metric in layer.metrics]


def build_snapshot(layer: SemanticLayer, catalog: CatalogSnapshot) -> CatalogSnapshot:
    """Resolve definitions and materialize typed semantic relationships."""
    validate_unique(layer)
    objects: list[CatalogObject] = []
    links: list[CatalogLink] = []
    assets = [item.asset_ref for item in catalog.objects]
    for metric in layer.metrics:
        card = _metric_card(metric, layer, assets)
        ref = AssetRef(asset_type="metric", asset_id=metric.id, version=str(metric.version))
        objects.append(
            CatalogObject(
                asset_ref=ref,
                name=metric.name,
                english_name=metric.english_name,
                source_id=metric.measure.table.split("/")[0],
                table_id=metric.measure.table,
                properties=JsonDocument(card.model_dump(mode="json")),
            )
        )
        links.extend(_metric_links(card))
    objects.extend(_owners(layer))
    for dimension in layer.dimensions:
        ref = AssetRef(asset_type="dimension", asset_id=dimension.id)
        objects.append(
            CatalogObject(
                asset_ref=ref,
                name=dimension.name,
                english_name=dimension.english_name,
                properties=JsonDocument(dimension.model_dump(mode="json")),
            )
        )
    for term in layer.terms:
        ref = AssetRef(asset_type="term", asset_id=f"term/{term.term}")
        objects.append(
            CatalogObject(
                asset_ref=ref,
                name=term.term,
                english_name=term.english_name,
                properties=JsonDocument(term.model_dump(mode="json")),
            )
        )
        links.append(
            CatalogLink(
                source=ref,
                kind="means",
                target=AssetRef(
                    asset_type=term.means.kind,
                    asset_id=term.means.id,
                ),
            )
        )
    return CatalogSnapshot(scope=SEMANTIC_SCOPE, objects=tuple(objects), links=tuple(links))


def _metric_card(
    metric: MetricDefinition, layer: SemanticLayer, assets: list[AssetRef]
) -> MetricCard:
    owner = next((item for item in layer.owners if item.name == metric.owner), None)
    return resolve_metric(metric, layer, assets).model_copy(
        update={"owner_english_name": owner.english_name if owner else None}
    )


def _owners(layer: SemanticLayer) -> list[CatalogObject]:
    owners = {item.name: item for item in layer.owners}
    return [
        CatalogObject(
            asset_ref=AssetRef(asset_type="owner", asset_id=f"owner/{owner}"),
            name=owner,
            english_name=owners[owner].english_name if owner in owners else None,
            properties=JsonDocument(owners[owner].model_dump(mode="json"))
            if owner in owners
            else JsonDocument({}),
        )
        for owner in sorted({item.owner for item in layer.metrics} | owners.keys())
    ]


def _metric_links(card: MetricCard) -> list[CatalogLink]:
    metric = card.definition
    ref = AssetRef(asset_type="metric", asset_id=metric.id, version=str(metric.version))
    columns = {metric.measure.column, *(item.column for item in metric.filters)}
    columns.add(metric.time.column)
    links = [
        CatalogLink(
            source=ref,
            kind="measures",
            target=AssetRef(
                asset_type="column",
                asset_id=column,
            ),
        )
        for column in sorted(columns)
    ]
    links.extend(
        CatalogLink(
            source=ref,
            kind="sliced_by",
            target=AssetRef(
                asset_type="dimension",
                asset_id=dimension,
            ),
        )
        for dimension in metric.dimensions
    )
    links.append(
        CatalogLink(
            source=ref,
            kind="owned_by",
            target=AssetRef(
                asset_type="owner",
                asset_id=f"owner/{metric.owner}",
            ),
        )
    )
    return links
