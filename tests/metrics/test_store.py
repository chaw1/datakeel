# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Semantic revisions remain idempotent, reversible, and event-replayable."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from datakeel.core.catalog_models import CatalogQuery, CatalogSnapshot
from datakeel.core.errors import ConflictError, NotFoundError
from datakeel.core.metric_models import SemanticLayer
from datakeel.storage.catalog_queries import get_object, read_objects
from datakeel.storage.catalog_store import publish_snapshot
from datakeel.storage.database import Database
from datakeel.storage.events import all_events
from datakeel.storage.metric_store import (
    get_metric,
    install_layer,
    list_metrics,
    metric_history,
    read_layer,
    rollback_metric_in_session,
    update_metric_in_session,
)


def test_install_layer_resolves_catalog_and_repeated_load_is_event_free(
    db: Database,
    layer: SemanticLayer,
    catalog: CatalogSnapshot,
) -> None:
    """Repeated identical YAML publishes no additional semantic event."""
    publish_snapshot(db, catalog)
    first = install_layer(db, layer)
    second = install_layer(db, layer)
    assert first.event_id is not None
    assert second.event_id is None
    assert list_metrics(db)[0].status == "resolved"
    assert read_layer(db) == layer


def test_metric_versions_restore_old_semantics_without_erasing_history(
    db: Database,
    layer: SemanticLayer,
    catalog: CatalogSnapshot,
) -> None:
    """A controlled revision and inverse produce three independently auditable versions."""
    publish_snapshot(db, catalog)
    install_layer(db, layer)
    definition = layer.metrics[0].model_copy(update={"owner": "Finance", "description": "Changed"})
    with db.session() as session:
        mutation = update_metric_in_session(session, definition, actor="reviewer")
        session.commit()
    assert mutation.before.definition.version == 1
    assert mutation.after.definition.version == 2
    assert mutation.event_id
    with pytest.raises(ConflictError, match="expected version 1; current is 2"):
        install_layer(db, layer)
    assert get_metric(db, "revenue").definition.owner == "Finance"
    with db.session() as session:
        result = rollback_metric_in_session(session, "revenue", 1)
        session.commit()
    assert result.after.definition.version == 3
    assert result.after.definition.owner == "Retail team"
    assert [card.definition.version for card in metric_history(db, "revenue")] == [1, 2, 3]


def test_metric_unknown_identity_and_revision_are_explicit(db: Database) -> None:
    """Missing references never silently select another metric or revision."""
    with pytest.raises(NotFoundError, match="Metric not found"):
        get_metric(db, "missing")
    with db.session() as session, pytest.raises(NotFoundError, match="revision not found"):
        rollback_metric_in_session(session, "missing", 1)


def test_install_layer_without_catalog_keeps_unresolved_metric(
    db: Database,
    layer: SemanticLayer,
) -> None:
    """Missing source metadata remains discoverable with actionable reasons."""
    install_layer(db, layer)
    card = get_metric(db, "revenue")
    assert card.status == "unresolved"
    assert "Missing column: test/main/orders/amount" in card.reasons


def test_install_changed_semantics_advances_authoritative_version(
    db: Database,
    layer: SemanticLayer,
    catalog: CatalogSnapshot,
) -> None:
    """A matching YAML expected version creates a fresh revision instead of replacing history."""
    publish_snapshot(db, catalog)
    install_layer(db, layer)
    changed = layer.model_copy(
        update={"metrics": [layer.metrics[0].model_copy(update={"owner": "Finance"})]}
    )
    install_layer(db, changed)
    assert get_metric(db, "revenue").definition.version == 2
    assert [card.definition.owner for card in metric_history(db, "revenue")] == [
        "Retail team",
        "Finance",
    ]
    expected = changed.model_copy(
        update={"metrics": [changed.metrics[0].model_copy(update={"version": 2})]}
    )
    assert install_layer(db, expected).event_id is None


def test_initial_yaml_and_action_expected_versions_are_enforced(
    db: Database,
    layer: SemanticLayer,
) -> None:
    """Neither initial import nor direct action updates may choose arbitrary version numbers."""
    wrong = layer.model_copy(
        update={"metrics": [layer.metrics[0].model_copy(update={"version": 7})]}
    )
    with pytest.raises(ConflictError, match="current is 1"):
        install_layer(db, wrong)
    install_layer(db, layer)
    with db.session() as session, pytest.raises(ConflictError, match="current is 1"):
        update_metric_in_session(session, wrong.metrics[0])


def test_concurrent_imports_cannot_publish_same_metric_version(
    db: Database,
    layer: SemanticLayer,
) -> None:
    """Concurrent imports with the same expected revision preserve one winner and all history."""
    install_layer(db, layer)
    start = Barrier(2)

    def attempt(owner: str) -> str:
        start.wait(timeout=10)
        updated = layer.model_copy(
            update={
                "metrics": [layer.metrics[0].model_copy(update={"owner": owner})],
            }
        )
        try:
            install_layer(db, updated)
        except ConflictError:
            return "conflict"
        return "published"

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(attempt, ["Finance", "Operations"]))
    assert sorted(outcomes) == ["conflict", "published"]
    assert [card.definition.version for card in metric_history(db, "revenue")] == [1, 2]


def test_current_metric_resolution_tracks_source_changes_without_rewriting_history(
    db: Database,
    layer: SemanticLayer,
    catalog: CatalogSnapshot,
) -> None:
    """Source fields change current resolution while semantic versions and history stay fixed."""
    publish_snapshot(db, catalog)
    install_layer(db, layer)
    missing = catalog.model_copy(
        update={
            "objects": tuple(
                item
                for item in catalog.objects
                if item.asset_ref.asset_id != "test/main/orders/amount"
            )
        }
    )
    publish_snapshot(db, missing)
    assert get_metric(db, "revenue").status == "unresolved"
    assert list_metrics(db)[0].status == "unresolved"
    assert get_metric(db, "revenue").definition.version == 1
    assert metric_history(db, "revenue")[0].status == "resolved"
    item = get_object(db, "revenue")
    assert item.properties.root["status"] == "unresolved"
    assert (
        read_objects(db, CatalogQuery(kind="metric")).items[0].properties.root["status"]
        == "unresolved"
    )
    with db.session() as session:
        event_count = len(all_events(session))
    get_metric(db, "revenue")
    with db.session() as session:
        assert len(all_events(session)) == event_count
    publish_snapshot(db, catalog)
    assert get_metric(db, "revenue").status == "resolved"
    assert get_object(db, "revenue").properties.root["status"] == "resolved"
    assert get_metric(db, "revenue").definition.version == 1
