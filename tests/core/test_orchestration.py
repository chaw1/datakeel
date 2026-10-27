# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""External namespace normalization preserves physical identity and boundary safety."""

import pytest

from datakeel.core.orchestration import (
    OpenLineageDataset,
    OpenLineageNamespace,
    normalized_namespace,
)
from datakeel.core.orchestration_catalog import dataset_from_uri, resolve_dataset


@pytest.mark.parametrize(
    ("namespace", "expected"),
    [
        ("POSTGRESQL://Warehouse.Example:5432/", "postgres://warehouse.example"),
        ("https://Warehouse.Example:8443/Case/", "https://warehouse.example:8443/Case"),
        ("http://[::1]:80/", "http://[::1]"),
        ("bigquery", "bigquery"),
        ("warehouse/", "warehouse"),
    ],
)
def test_namespace_canonicalizes_transport_without_folding_paths(
    namespace: str, expected: str
) -> None:
    """Equivalent URI authorities share identity while URI paths retain case."""
    assert normalized_namespace(namespace) == expected


@pytest.mark.parametrize("namespace", [" ", "postgres://user:secret@warehouse.example"])
def test_namespace_rejects_blank_or_credentialed_namespace(namespace: str) -> None:
    """Dataset metadata cannot carry connection credentials in its namespace."""
    with pytest.raises(ValueError, match="must not"):
        normalized_namespace(namespace)


def test_dataset_mapping_respects_database_boundary_and_name_case() -> None:
    """Explicit source mappings apply only to their configured database."""
    mappings = {
        "postgres://warehouse.example": OpenLineageNamespace(source_id="physical", database="one")
    }
    matching = resolve_dataset(
        OpenLineageDataset(namespace="postgres://warehouse.example", name="one.public.Orders"),
        mappings,
    )
    other = resolve_dataset(
        OpenLineageDataset(namespace="postgres://warehouse.example", name="two.public.Orders"),
        mappings,
    )
    assert matching.source_id == "physical"
    assert other.source_id != "physical"
    assert matching.relation.name == "Orders"


def test_nonrelational_dataset_names_keep_dots_and_uri_path() -> None:
    """Object names containing periods are not accidentally split into database fields."""
    dataset = dataset_from_uri("s3://bucket.example/events/2026.json")
    resolved = resolve_dataset(dataset, {})
    assert dataset.name == "events/2026.json"
    assert resolved.relation.name == "events/2026.json"
    assert resolved.relation.schema_name == "default"
    assert dataset_from_uri("opaque-dataset").namespace == "airflow-dataset"


@pytest.mark.parametrize(
    ("namespace", "name"),
    [
        ("file", "/srv/exports/visits.v2.csv"),
        ("file://etl-host", "/srv/exports/visits.v2.csv"),
        ("dbfs://clinic-workspace", "/mnt/exports/visits.delta"),
    ],
)
def test_path_dataset_names_from_naming_spec_are_not_split_on_dots(
    namespace: str, name: str
) -> None:
    """Local and DBFS file paths keep the whole path as the dataset name."""
    resolved = resolve_dataset(OpenLineageDataset(namespace=namespace, name=name), {})
    assert resolved.relation.name == name
    assert resolved.relation.schema_name == "default"
    assert resolved.relation.database is None


def test_airflow_file_uri_without_host_keeps_the_local_path() -> None:
    """file:///path dataset URIs map to the bare local-file namespace, not one opaque name."""
    dataset = dataset_from_uri("file:///srv/exports/visits.v2.csv")
    assert (dataset.namespace, dataset.name) == ("file", "/srv/exports/visits.v2.csv")
    assert resolve_dataset(dataset, {}).relation.name == "/srv/exports/visits.v2.csv"
