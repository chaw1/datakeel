# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Import real v10, v11 and v12 artifacts of one project and adapter-specific variants."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from datakeel.catalog.importers.dbt import prepare_dbt, sql_dialect
from datakeel.catalog.metadata_service import import_dbt
from datakeel.catalog.service import import_catalog
from datakeel.core.catalog_models import CatalogImportRequest, CatalogObject, CatalogQuery
from datakeel.core.metadata_imports import DbtImportRequest, ExternalMetadata
from datakeel.core.models import JsonDocument
from datakeel.storage.catalog_queries import get_object, read_objects

if TYPE_CHECKING:
    from pydantic import JsonValue

    from datakeel.storage.database import Database

_FIXTURES = Path(__file__).parents[1] / "fixtures" / "dbt-fleet"
_VERSIONS = ("v10", "v11", "v12")


def _artifacts(version: str) -> DbtImportRequest:
    folder = _FIXTURES / version
    return DbtImportRequest(
        source_id="fleet",
        manifest=JsonDocument.model_validate_json((folder / "manifest.json").read_text()),
        catalog=JsonDocument.model_validate_json((folder / "catalog.json").read_text()),
        run_results=JsonDocument.model_validate_json((folder / "run_results.json").read_text()),
    )


def _objects(request: DbtImportRequest) -> dict[str, CatalogObject]:
    return {item.asset_ref.asset_id: item for item in prepare_dbt(request).snapshot.objects}


def _metadata(item: CatalogObject) -> ExternalMetadata:
    return ExternalMetadata.model_validate(item.properties.root["integration"])


def _test_states(item: CatalogObject) -> dict[str, JsonValue]:
    tests = _metadata(item).details.root["tests"]
    assert isinstance(tests, list)
    states: dict[str, JsonValue] = {}
    for test in tests:
        assert isinstance(test, dict)
        result = test.get("result")
        states[str(test["unique_id"]).split(".")[2]] = (
            result.get("status") if isinstance(result, dict) else None
        )
    return states


@pytest.mark.parametrize("version", _VERSIONS)
def test_fleet_artifacts_when_imported_keep_owners_tags_and_descriptions(version: str) -> None:
    """Every supported manifest version yields the same documented resource metadata."""
    objects = _objects(_artifacts(version))
    trips = objects["fleet/main/fact_trips"]
    assert trips.name == "fact_trips"
    assert _metadata(trips).owner == "ops-analytics"
    assert _metadata(trips).tags == ("finance", "mart")
    assert trips.properties.root["comment"] == "One row per valid trip with driver and capacity"
    assert objects["fleet/main/fact_trips/distance_km"].properties.root["comment"] == (
        "Distance in kilometres"
    )
    assert _metadata(objects["fleet/main/driver_daily"]).owner == "fleet-finance"
    assert _metadata(objects["fleet/main/raw_trip_log"]).owner == "ingest-team"
    assert _metadata(objects["fleet/main/vehicle_types"]).tags == ("reference",)
    staging = objects["fleet/main_staging/stg_trips"]
    assert staging.properties.root["is_view"] is True
    assert _metadata(objects["fleet/snapshots/driver_history"]).details.root["materialized"] == (
        "snapshot"
    )


@pytest.mark.parametrize("version", _VERSIONS)
def test_fleet_artifacts_when_compiled_trace_fields_through_ephemeral_ctes(version: str) -> None:
    """Inlined ephemeral CTEs and star projections still resolve to physical fields."""
    batch = prepare_dbt(_artifacts(version))
    edges = {
        (link.source.asset_id, link.target.asset_id)
        for link in batch.snapshot.links
        if link.kind == "derived"
    }
    assert {
        ("fleet/main/raw_driver_roster/full_name", "fleet/main/fact_trips/driver_name"),
        ("fleet/main/vehicle_types/capacity", "fleet/main/fact_trips/vehicle_capacity"),
        ("fleet/main_staging/stg_trips/started_at", "fleet/main/fact_trips/trip_date"),
        ("fleet/main/fact_trips/distance_km", "fleet/main/driver_daily/total_km"),
        ("fleet/main/raw_trip_log/trip_id", "fleet/main_staging/stg_trips/trip_id"),
        ("fleet/main_staging/stg_drivers", "fleet/main/fact_trips"),
        ("fleet/main/fact_trips", "fleet/dbt-exposure/exposure.fleet.fleet_dashboard"),
        ("fleet/main/driver_daily", "fleet/dbt-exposure/exposure.fleet.fleet_dashboard"),
    } <= edges
    assert [failure.origin for failure in batch.parse_failures] == [
        "model.fleet.metricflow_time_spine#1"
    ]


@pytest.mark.parametrize("version", _VERSIONS)
def test_fleet_artifacts_when_tests_ran_keep_pass_and_warn_results(version: str) -> None:
    """Singular warnings and multi-parent relationships remain on every tested table."""
    objects = _objects(_artifacts(version))
    raw = _test_states(objects["fleet/main/raw_trip_log"])
    assert raw["assert_trip_distance_positive"] == "warn"
    assert raw["source_unique_raw_trips_trip_id"] == "pass"
    relationship = "relationships_fct_trips_driver_id__driver_id__source_raw_drivers_"
    assert _test_states(objects["fleet/main/fact_trips"])[relationship] == "pass"
    assert _test_states(objects["fleet/main/raw_driver_roster"])[relationship] == "pass"
    staging = _test_states(objects["fleet/main_staging/stg_trips"])
    assert ("stg_trips" in staging) is (version == "v12")


@pytest.mark.parametrize("version", _VERSIONS)
def test_fleet_artifacts_when_semantics_present_only_convert_simple_metrics(version: str) -> None:
    """A plain measure gets a suggested definition; a filtered metric stays raw."""
    objects = _objects(_artifacts(version))
    simple = objects["fleet/dbt-draft/metric.fleet.fleet_distance"].properties.root
    filtered = objects["fleet/dbt-draft/metric.fleet.long_trip_count"].properties.root
    assert simple["status"] == "draft"
    definition = simple["definition"]
    assert isinstance(definition, dict)
    assert definition["measure"] == {
        "table": "fleet/main/fact_trips",
        "column": "fleet/main/fact_trips/distance_km",
        "aggregation": "sum",
    }
    assert filtered["definition"] is None
    exposure = objects["fleet/dbt-exposure/exposure.fleet.fleet_dashboard"]
    assert _metadata(exposure).owner == "bi-owner@example.org"


def test_fleet_artifacts_when_database_already_imported_merge_physical_tables(
    db: Database, tmp_path: Path
) -> None:
    """A database import of the same warehouse keeps one table with both contributions."""
    path = tmp_path / "fleet.sqlite"
    with sqlite3.connect(path) as connection:
        connection.executescript(
            "CREATE TABLE fact_trips(trip_id INTEGER PRIMARY KEY, driver_name TEXT,"
            " distance_km DOUBLE);"
            "CREATE TABLE raw_trip_log(trip_id INTEGER PRIMARY KEY, distance_km DOUBLE);"
        )
    import_catalog(
        db,
        CatalogImportRequest(source_id="fleet", name="Fleet", connection_url=f"sqlite:///{path}"),
    )
    report = import_dbt(db, _artifacts("v11"))
    assert report.failed_sql_count == 1
    tables = read_objects(db, CatalogQuery(kind="table", source_id="fleet")).items
    assert sum(item.asset_ref.asset_id == "fleet/main/fact_trips" for item in tables) == 1
    merged = get_object(db, "fleet/main/fact_trips")
    assert merged.properties.root["primary_key"] == ["trip_id"]
    assert _metadata(merged).owner == "ops-analytics"
    assert import_dbt(db, _artifacts("v11")).unchanged == report.object_count


@pytest.mark.parametrize(
    ("adapter", "expected"),
    [
        ("postgres", "postgres"),
        ("Snowflake", "snowflake"),
        ("sqlserver", "tsql"),
        ("synapse", "tsql"),
        ("glue", "spark"),
        ("unlisted-warehouse", ""),
        (None, ""),
    ],
)
def test_adapter_dialect_when_mapped_uses_parser_name_or_generic_sql(
    adapter: str | None, expected: str
) -> None:
    """Adapter names absent from the SQL parser degrade to generic SQL, not a failure."""
    assert sql_dialect(adapter) == expected


def _single_model(metadata: dict[str, JsonValue], **fields: JsonValue) -> DbtImportRequest:
    return DbtImportRequest(
        source_id="shop",
        manifest=JsonDocument(
            {
                "metadata": {
                    "dbt_schema_version": "https://schemas.getdbt.com/dbt/manifest/v12.json",
                    **metadata,
                },
                "nodes": {
                    "model.shop.orders": {
                        "unique_id": "model.shop.orders",
                        "name": "orders",
                        "resource_type": "model",
                        "schema": "dbo",
                        "relation_name": "[warehouse].[dbo].[orders]",
                        **fields,
                    }
                },
            }
        ),
    )


def test_unknown_adapter_when_imported_keeps_artifact_dialect_name() -> None:
    """Bracket-quoted relations parse for SQL Server and the source keeps the adapter."""
    objects = _objects(
        _single_model({"adapter_type": "sqlserver"}, config={"tags": "nightly"}, columns={})
    )
    assert objects["shop"].properties.root["dialect"] == "sqlserver"
    assert _metadata(objects["shop/dbo/orders"]).tags == ("nightly",)


def test_missing_adapter_when_imported_uses_generic_parser_and_unknown_dialect() -> None:
    """Older or hand-trimmed manifests without adapter_type still import."""
    request = _single_model(
        {"adapter_type": None}, relation_name='"warehouse"."dbo"."orders"', columns={}
    )
    objects = _objects(request)
    assert objects["shop"].properties.root["dialect"] == "unknown"
    assert "shop/dbo/orders" in objects
