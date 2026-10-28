# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Keep unsupported dbt semantics as editable drafts without changing their meaning."""

from pathlib import Path

import pytest
from pydantic import JsonValue

from datakeel.catalog.importers.dbt import prepare_dbt
from datakeel.core.errors import ValidationError
from datakeel.core.metadata_imports import DbtImportRequest, MetricDraft
from datakeel.core.models import JsonDocument


def _request(
    metric_changes: dict[str, JsonValue] | None = None,
    semantic_changes: dict[str, JsonValue] | None = None,
) -> DbtImportRequest:
    metric: dict[str, JsonValue] = {
        "unique_id": "metric.shop.revenue",
        "name": "Revenue",
        "resource_type": "metric",
        "type": "simple",
        "type_params": {"measure": {"name": "revenue"}},
        **(metric_changes or {}),
    }
    semantic: dict[str, JsonValue] = {
        "unique_id": "semantic_model.shop.orders",
        "name": "Orders",
        "resource_type": "semantic_model",
        "config": {"meta": {"owner": "Finance"}},
        "depends_on": {"nodes": ["model.shop.orders"]},
        "defaults": {"agg_time_dimension": "ordered_at"},
        "measures": [{"name": "revenue", "expr": "amount", "agg": "sum"}],
        "dimensions": [
            {"name": "ordered_at", "type": "time", "type_params": {"time_granularity": "day"}}
        ],
        **(semantic_changes or {}),
    }
    return DbtImportRequest(
        source_id="shop",
        manifest=JsonDocument(
            {
                "metadata": {
                    "dbt_schema_version": "https://schemas.getdbt.com/dbt/manifest/v12.json"
                },
                "nodes": {
                    "model.shop.orders": {
                        "unique_id": "model.shop.orders",
                        "name": "orders",
                        "resource_type": "model",
                        "columns": {
                            "amount": {"name": "amount"},
                            "ordered_at": {"name": "ordered_at"},
                        },
                    }
                },
                "semantic_models": {"semantic_model.shop.orders": semantic},
                "metrics": {"metric.shop.revenue": metric},
            }
        ),
    )


def _metric(request: DbtImportRequest) -> MetricDraft:
    return next(
        MetricDraft.model_validate(item.properties.root)
        for item in prepare_dbt(request).snapshot.objects
        if item.asset_ref.asset_type == "metric_draft" and item.name == "Revenue"
    )


@pytest.mark.parametrize("measure", ["revenue", {"name": "revenue"}])
def test_simple_metric_when_supported_retains_raw_and_explicit_time_grain(
    measure: JsonValue,
) -> None:
    """Map both documented simple-measure reference forms without activating either draft."""
    request = _request({"type_params": {"measure": measure}})
    draft = _metric(request)
    assert draft.status == "draft"
    assert draft.definition is not None
    assert draft.definition.measure.column == "shop/main/orders/amount"
    assert draft.definition.time.granularity == "day"
    assert draft.raw.root["type_params"] == {"measure": measure}


@pytest.mark.parametrize(
    "changes",
    [
        {"type": "ratio"},
        {"filter": {"where_sql_template": "amount > 0"}},
        {"type_params": {}},
        {"type_params": {"measure": None}},
        {"type_params": {"measure": {"name": "revenue", "filter": "amount > 0"}}},
        {"type_params": {"measure": {"name": "revenue", "join_to_timespine": True}}},
        {"type_params": {"measure": {"name": "revenue", "fill_nulls_with": 0}}},
    ],
)
def test_metric_when_meaning_cannot_be_mapped_retains_unresolved_draft(
    changes: dict[str, JsonValue],
) -> None:
    """Never erase filters, ratios, time-spine behavior, or filling rules during conversion."""
    draft = _metric(_request(changes))
    assert draft.definition is None
    assert all(draft.raw.root[key] == value for key, value in changes.items())


@pytest.mark.parametrize(
    "changes",
    [
        {"config": {}},
        {"defaults": {}},
        {"dimensions": []},
        {"dimensions": [{"name": "ordered_at", "type": "categorical"}]},
        {
            "dimensions": [
                {"name": "ordered_at", "type": "time", "type_params": {"time_granularity": "hour"}}
            ]
        },
        {"measures": [{"name": "revenue", "expr": "amount * 2", "agg": "sum"}]},
        {"measures": [{"name": "revenue", "expr": "amount", "agg": "median"}]},
        {
            "measures": [
                {
                    "name": "revenue",
                    "expr": "amount",
                    "agg": "sum",
                    "agg_params": {"percentile": 0.5},
                }
            ]
        },
        {
            "measures": [
                {
                    "name": "revenue",
                    "expr": "amount",
                    "agg": "sum",
                    "non_additive_dimension": {"name": "ordered_at"},
                }
            ]
        },
        {"depends_on": {"nodes": ["model.shop.missing"]}},
    ],
)
def test_semantic_model_when_context_is_incomplete_needs_human_definition(
    changes: dict[str, JsonValue],
) -> None:
    """Reject guessed owners, fields, time grains, unsupported aggregates, and missing models."""
    draft = _metric(_request(semantic_changes=changes))
    assert draft.definition is None
    assert draft.status == "draft"


def test_semantic_model_when_measure_name_is_ambiguous_needs_human_definition() -> None:
    """Require an unambiguous measure origin rather than relying on manifest ordering."""
    request = _request(
        semantic_changes={
            "measures": [
                {"name": "revenue", "expr": "amount", "agg": "sum"},
                {"name": "revenue", "expr": "amount", "agg": "avg"},
            ]
        }
    )
    assert _metric(request).definition is None


def test_semantic_model_when_time_grain_is_month_preserves_native_grain() -> None:
    """Do not silently downsample a semantic model's explicit time precision."""
    request = _request(
        semantic_changes={
            "dimensions": [
                {"name": "ordered_at", "type": "time", "type_params": {"time_granularity": "month"}}
            ]
        }
    )
    definition = _metric(request).definition
    assert definition is not None
    assert definition.time.granularity == "month"


def test_semantic_model_when_collection_malformed_reports_error() -> None:
    """A malformed semantic collection cannot silently disappear from an import."""
    request = _request()
    request.manifest.root["semantic_models"] = []
    with pytest.raises(ValidationError, match="semantic_models must be an object"):
        prepare_dbt(request)


def test_real_semantics_when_measure_changes_invalidates_metric_source_fingerprint() -> None:
    """Bind approval provenance to the referenced semantic model, not just its measure name."""
    fixtures = Path(__file__).parents[1] / "fixtures" / "dbt"
    request = DbtImportRequest(
        source_id="shop",
        manifest=JsonDocument.model_validate_json((fixtures / "manifest.json").read_text()),
        catalog=JsonDocument.model_validate_json((fixtures / "catalog.json").read_text()),
    )
    before = _real_metric(request)
    semantic_models = request.manifest.root["semantic_models"]
    assert isinstance(semantic_models, dict)
    semantic = semantic_models["semantic_model.p22_shop.order_semantics"]
    assert isinstance(semantic, dict)
    measures = semantic["measures"]
    assert isinstance(measures, list)
    measure = measures[0]
    assert isinstance(measure, dict)
    measure["expr"] = "order_id"
    after = _real_metric(request)
    assert before.raw == after.raw
    assert before.definition != after.definition
    assert before.source_fingerprint
    assert before.source_fingerprint != after.source_fingerprint


def _real_metric(request: DbtImportRequest) -> MetricDraft:
    return next(
        MetricDraft.model_validate(item.properties.root)
        for item in prepare_dbt(request).snapshot.objects
        if item.asset_ref.asset_type == "metric_draft" and item.name == "total_revenue"
    )


def test_semantics_when_manifest_order_changes_keeps_source_fingerprint() -> None:
    """Canonicalize resource enumeration so equivalent artifacts preserve an approval."""
    request = _request()
    semantic_models = request.manifest.root["semantic_models"]
    assert isinstance(semantic_models, dict)
    semantic = semantic_models["semantic_model.shop.orders"]
    assert isinstance(semantic, dict)
    semantic_models["semantic_model.shop.other"] = {
        **semantic,
        "unique_id": "semantic_model.shop.other",
        "name": "Other",
        "measures": [],
    }
    before = _metric(request)
    reordered_manifest = dict(reversed(tuple(request.manifest.root.items())))
    reordered_manifest["semantic_models"] = dict(reversed(tuple(semantic_models.items())))
    reversed_request = request.model_copy(update={"manifest": JsonDocument(reordered_manifest)})
    assert _metric(reversed_request).source_fingerprint == before.source_fingerprint
