# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Read standard manifest-v12 unit tests beside existing data-test quality evidence."""

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pydantic import JsonValue

from datakeel.catalog.importers.dbt import prepare_dbt
from datakeel.core.metadata_imports import DbtImportRequest, ExternalMetadata
from datakeel.core.models import JsonDocument


def _request(status: str | None) -> DbtImportRequest:
    manifest = JsonDocument(
        {
            "metadata": {"dbt_schema_version": "https://schemas.getdbt.com/dbt/manifest/v12.json"},
            "nodes": {
                "model.shop.orders": {
                    "name": "orders",
                    "resource_type": "model",
                    "unique_id": "model.shop.orders",
                },
                "test.shop.not_null": {
                    "name": "not_null",
                    "resource_type": "test",
                    "unique_id": "test.shop.not_null",
                    "depends_on": {"nodes": ["model.shop.orders"]},
                },
            },
            "unit_tests": {
                "unit_test.shop.orders.valid_revenue": {
                    "unique_id": "unit_test.shop.orders.valid_revenue",
                    "name": "valid_revenue",
                    "resource_type": "unit_test",
                    "model": "orders",
                    "schema": None,
                    "depends_on": {"nodes": ["model.shop.orders"]},
                    "given": [{"input": "source('shop', 'orders')", "rows": [{"amount": 15}]}],
                    "expect": {"rows": [{"amount": 15}]},
                }
            },
        }
    )
    results: list[JsonValue] = [{"unique_id": "test.shop.not_null", "status": "pass"}]
    if status:
        results.append(
            {
                "unique_id": "unit_test.shop.orders.valid_revenue",
                "status": status,
                "failures": int(status == "fail"),
            }
        )
    return DbtImportRequest(
        source_id="shop", manifest=manifest, run_results=JsonDocument({"results": results})
    )


@pytest.mark.parametrize("status", ["pass", "fail", None])
def test_unit_tests_when_v12_with_null_schema_preserve_definition_and_available_result(
    status: str | None,
) -> None:
    """Retain static-input assertions and mix both test types without fabricating a result."""
    request = _request(status)
    snapshot = prepare_dbt(request).snapshot
    table = next(item for item in snapshot.objects if item.asset_ref.asset_type == "table")
    metadata = ExternalMetadata.model_validate(table.properties.root["integration"])
    tests = metadata.details.root["tests"]
    assert isinstance(tests, list)
    assert len(tests) == 2
    evidence = next(
        test
        for test in tests
        if isinstance(test, dict) and test["unique_id"] == "unit_test.shop.orders.valid_revenue"
    )
    assert isinstance(evidence, dict)
    definition = evidence["definition"]
    assert isinstance(definition, dict)
    assert definition["schema"] is None
    assert definition["given"] == [{"input": "source('shop', 'orders')", "rows": [{"amount": 15}]}]
    assert definition["expect"] == {"rows": [{"amount": 15}]}
    if status:
        assert evidence["result"]["status"] == status
    else:
        assert "result" not in evidence


@pytest.mark.parametrize("version", [10, 11])
def test_unit_tests_when_collection_absent_in_older_schema_keeps_data_tests(version: int) -> None:
    """Keep v10 and v11 backward-compatible without requiring a v12-only resource collection."""
    request = _request("pass")
    request.manifest.root.pop("unit_tests")
    request.manifest.root["metadata"] = {
        "dbt_schema_version": f"https://schemas.getdbt.com/dbt/manifest/v{version}.json"
    }
    snapshot = prepare_dbt(request).snapshot
    table = next(item for item in snapshot.objects if item.asset_ref.asset_type == "table")
    metadata = ExternalMetadata.model_validate(table.properties.root["integration"])
    tests = metadata.details.root["tests"]
    assert isinstance(tests, list)
    assert len(tests) == 1
    assert tests[0]["unique_id"] == "test.shop.not_null"
