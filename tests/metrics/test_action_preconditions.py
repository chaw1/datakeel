# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Controlled metric plans require resolved references while YAML imports remain permissive."""

from pathlib import Path

import pytest
import yaml
from sqlalchemy import select

from datakeel.actions.registry import action_definition
from datakeel.actions.service import prepare_action
from datakeel.api.app import create_app
from datakeel.core.catalog_models import CatalogSnapshot
from datakeel.core.errors import ValidationError
from datakeel.core.metric_models import MetricDefinition, MetricFilter, MetricTime, SemanticLayer
from datakeel.core.models import JsonDocument
from datakeel.metrics.loader import load_layer
from datakeel.storage.action_rows import ActionPlanRow
from datakeel.storage.catalog_store import publish_snapshot
from datakeel.storage.database import Database
from datakeel.storage.metric_store import get_metric, install_layer
from tests.asgi_client import TestClient


@pytest.fixture
def registered(db: Database, layer: SemanticLayer, catalog: CatalogSnapshot) -> MetricDefinition:
    """Install one resolved metric and all its catalog dependencies."""
    publish_snapshot(db, catalog)
    install_layer(db, layer)
    return layer.metrics[0]


def test_prepare_metric_when_multiple_references_missing_reports_each_without_plan(
    db: Database, registered: MetricDefinition
) -> None:
    """The HTTP boundary lists every missing reference before any plan is persisted."""
    changed = registered.model_copy(
        update={
            "measure": registered.measure.model_copy(
                update={"column": "test/main/orders/missing_amount"}
            ),
            "filters": [MetricFilter(column="test/main/orders/missing_filter", value=1)],
            "time": MetricTime(column="test/main/orders/missing_time"),
            "dimensions": ["missing_dimension"],
        }
    )
    with TestClient(create_app(db)) as client:
        response = client.post(
            "/api/actions/update_metric/prepare",
            json={"definition": changed.model_dump(mode="json")},
        )
    assert response.status_code == 422
    assert response.json()["detail"].splitlines() == [
        "Metric revenue has unresolved catalog references:",
        "- Missing column: test/main/orders/missing_amount",
        "- Missing column: test/main/orders/missing_filter",
        "- Missing column: test/main/orders/missing_time",
        "- Unknown dimension: missing_dimension",
    ]
    with db.session() as session:
        assert session.scalars(select(ActionPlanRow)).all() == []
    assert get_metric(db, registered.id).definition == registered


@pytest.mark.parametrize(
    ("identity", "kind"),
    [
        ("test/main/orders", "table"),
        ("test/main/orders/amount", "column"),
        ("test/main/orders/date", "column"),
        ("test/main/orders/region", "column"),
    ],
)
def test_prepare_metric_when_catalog_reference_removed_rejects_current_definition(
    db: Database,
    registered: MetricDefinition,
    catalog: CatalogSnapshot,
    identity: str,
    kind: str,
) -> None:
    """Measure tables, measure fields, temporal fields, and dimension fields are all checked."""
    publish_snapshot(
        db,
        catalog.model_copy(
            update={
                "objects": tuple(
                    item for item in catalog.objects if item.asset_ref.asset_id != identity
                )
            }
        ),
    )
    with pytest.raises(ValidationError, match=f"Missing {kind}: {identity}"):
        prepare_action(
            db, "update_metric", JsonDocument({"definition": registered.model_dump(mode="json")})
        )
    with db.session() as session:
        assert session.scalars(select(ActionPlanRow)).all() == []


def test_prepare_metric_when_measure_resolved_persists_plan_without_changing_definition(
    db: Database, registered: MetricDefinition
) -> None:
    """A changed measure that references an existing field still yields a reviewable plan."""
    changed = registered.model_copy(
        update={
            "measure": registered.measure.model_copy(update={"column": "test/main/orders/region"})
        }
    )
    plan = prepare_action(
        db, "update_metric", JsonDocument({"definition": changed.model_dump(mode="json")})
    )
    with db.session() as session:
        assert session.get(ActionPlanRow, plan.id) is not None
    assert plan.canonical_params["definition"] == changed.model_dump(mode="json")
    assert "metric catalog references resolve" in action_definition("update_metric").preconditions
    assert get_metric(db, registered.id).definition == registered


def test_import_yaml_when_measure_missing_registers_unresolved_metric(
    db: Database, layer: SemanticLayer, catalog: CatalogSnapshot, tmp_path: Path
) -> None:
    """Import retains an invalid definition for repair without allowing a controlled plan."""
    definition = layer.metrics[0]
    changed = definition.model_copy(
        update={
            "measure": definition.measure.model_copy(update={"column": "test/main/orders/absent"})
        }
    )
    path = tmp_path / "unresolved.yaml"
    path.write_text(
        yaml.safe_dump(layer.model_copy(update={"metrics": [changed]}).model_dump(mode="json"))
    )
    publish_snapshot(db, catalog)
    report = install_layer(db, load_layer(path))
    card = get_metric(db, definition.id)
    assert report.event_id is not None
    assert card.definition == changed
    assert card.status == "unresolved"
    assert card.reasons == ["Missing column: test/main/orders/absent"]
