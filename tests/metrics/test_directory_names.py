# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Optional directory display metadata survives semantic publication and replay."""

from pathlib import Path

import pytest
import yaml
from pydantic import JsonValue

from datakeel.core.catalog_models import CatalogSnapshot
from datakeel.core.errors import ValidationError
from datakeel.core.metric_models import OwnerDefinition, SemanticLayer
from datakeel.core.models import JsonDocument
from datakeel.metrics.loader import load_layer
from datakeel.metrics.projection import (
    build_snapshot,
    metric_cards,
    resolved_metric_cards,
    semantic_layer,
)
from datakeel.storage.catalog_projection import projection_hash, rebuild_catalog
from datakeel.storage.catalog_store import publish_snapshot
from datakeel.storage.database import Database
from datakeel.storage.events import all_events
from datakeel.storage.metric_store import get_metric, install_layer, metric_history, read_layer


def _legacy_value(value: JsonValue) -> JsonValue:
    if isinstance(value, dict):
        return {
            key: _legacy_value(item)
            for key, item in value.items()
            if key not in {"english_name", "owner_english_name"}
        }
    if isinstance(value, list):
        return [_legacy_value(item) for item in value]
    return value


def test_directory_names_when_present_round_trip_without_changing_owner_identity(
    layer: SemanticLayer, catalog: CatalogSnapshot
) -> None:
    """English labels are metadata and never become relationship identities."""
    layer = layer.model_copy(
        update={
            "metrics": [layer.metrics[0].model_copy(update={"english_name": "Retail total"})],
            "dimensions": [
                layer.dimensions[0].model_copy(update={"english_name": "Trading region"})
            ],
            "terms": [layer.terms[0].model_copy(update={"english_name": "Retail turnover"})],
            "owners": [OwnerDefinition(name="Retail team", english_name="Retail operations")],
        }
    )
    snapshot = build_snapshot(layer, catalog)
    assert semantic_layer(snapshot) == layer
    names = {item.asset_ref.asset_type: item.english_name for item in snapshot.objects}
    assert names == {
        "metric": "Retail total",
        "dimension": "Trading region",
        "term": "Retail turnover",
        "owner": "Retail operations",
    }
    owner_link = next(link for link in snapshot.links if link.kind == "owned_by")
    assert owner_link.target.asset_id == "owner/Retail team"
    current = snapshot.model_copy(update={"objects": catalog.objects + snapshot.objects})
    card = resolved_metric_cards(current)[0]
    assert card.definition.owner == "Retail team"
    assert card.owner_english_name == "Retail operations"
    assert metric_cards(snapshot) == [card]


def test_directory_names_when_omitted_preserve_legacy_names(
    layer: SemanticLayer, catalog: CatalogSnapshot
) -> None:
    """Older semantic files keep reading without new display fields."""
    snapshot = build_snapshot(layer, catalog)
    assert semantic_layer(snapshot) == layer
    assert all(item.english_name is None for item in snapshot.objects)
    assert resolved_metric_cards(snapshot)[0].owner_english_name is None


def test_owner_metadata_when_merged_loads_and_rejects_duplicate_names(tmp_path: Path) -> None:
    """Directory owners share the same strict cross-file identity validation."""
    owner = {"name": "负责人", "english_name": "Catalog owner"}
    (tmp_path / "owners.yaml").write_text(yaml.safe_dump({"owners": [owner]}))
    layer = load_layer(tmp_path)
    assert layer.owners == [OwnerDefinition.model_validate(owner)]
    assert semantic_layer(build_snapshot(layer, CatalogSnapshot(scope="empty"))) == layer
    (tmp_path / "duplicate.yaml").write_text(yaml.safe_dump({"owners": [owner]}))
    with pytest.raises(ValidationError, match="Duplicate owner"):
        load_layer(tmp_path)


def test_old_snapshot_when_optional_labels_missing_reinstall_adds_no_event(
    db: Database, layer: SemanticLayer, catalog: CatalogSnapshot
) -> None:
    """Replay pre-label JSON and preserve unchanged-import identity and projection hashes."""
    snapshot = build_snapshot(layer, catalog)
    legacy_json = _legacy_value(JsonDocument(snapshot.model_dump(mode="json")).root)
    legacy = CatalogSnapshot.model_validate(legacy_json)
    publish_snapshot(db, catalog)
    publish_snapshot(db, legacy, operator="METRIC_CHANGE")
    before_hash = projection_hash(db)
    with db.session() as session:
        before_events = len(all_events(session))

    result = install_layer(db, layer)

    assert result.changed == 0
    assert result.unchanged == len(legacy.objects)
    assert result.event_id is None
    assert read_layer(db) == layer
    assert projection_hash(db) == before_hash
    with db.session() as session:
        assert len(all_events(session)) == before_events
    assert rebuild_catalog(db, before_hash).matches


@pytest.mark.parametrize("english", ["Retail operations", None])
def test_metric_cards_when_published_keep_current_and_history_owner_labels_equal(
    db: Database, layer: SemanticLayer, catalog: CatalogSnapshot, english: str | None
) -> None:
    """Current and historical cards share the owner metadata frozen at publication."""
    layer = layer.model_copy(
        update={"owners": [OwnerDefinition(name="Retail team", english_name=english)]}
    )
    publish_snapshot(db, catalog)
    install_layer(db, layer)
    current = get_metric(db, layer.metrics[0].id)
    history = metric_history(db, current.definition.id)
    assert history == [current]
    assert current.owner_english_name == english
    assert rebuild_catalog(db).matches
    assert metric_history(db, current.definition.id) == [get_metric(db, current.definition.id)]
