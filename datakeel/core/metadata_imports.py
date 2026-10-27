# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Frozen metadata integration boundaries without changing existing catalog schemas."""

from typing import Literal

from pydantic import Field

from datakeel.core.catalog_models import CatalogSnapshot, ImportReport, SqlFailure
from datakeel.core.metric_models import MetricDefinition
from datakeel.core.models import BoundaryModel, JsonDocument


class PhysicalRelation(BoundaryModel):
    """Identify a physical relation independently of an orchestration node name."""

    database: str | None = None
    schema_name: str
    name: str
    namespace: str | None = None


class ExternalMetadata(BoundaryModel):
    """Keep one adapter's provenance and descriptive evidence on a catalog object."""

    system: Literal["dbt", "airflow", "openlineage"]
    unique_id: str
    description: str | None = None
    owner: str | None = None
    tags: tuple[str, ...] = ()
    relation: PhysicalRelation | None = None
    source_deleted: bool = False
    details: JsonDocument = Field(default_factory=lambda: JsonDocument({}))


class DbtImportRequest(BoundaryModel):
    """Supply decoded dbt artifacts and the matching physical catalog source identity."""

    source_id: str = Field(min_length=1)
    name: str = Field(default="dbt", min_length=1)
    manifest: JsonDocument
    catalog: JsonDocument | None = None
    run_results: JsonDocument | None = None


class AirflowImportRequest(BoundaryModel):
    """Supply an offline Airflow REST v1 export and a stable import source identity."""

    source_id: str = Field(min_length=1)
    name: str = Field(default="Airflow", min_length=1)
    document: JsonDocument


class AirflowSource(BoundaryModel):
    """Name the catalog source and optional DAG subset for a live REST v1 import."""

    source_id: str = Field(min_length=1)
    name: str = Field(default="Airflow", min_length=1)
    dag_ids: tuple[str, ...] = ()
    actor: str = "local-user"


class MetadataImportBatch(BoundaryModel):
    """Return adapter snapshots and SQL diagnostics before starting a transaction."""

    snapshot: CatalogSnapshot
    parse_failures: tuple[SqlFailure, ...] = ()


class MetadataImportReport(ImportReport):
    """Add explicit soft deletion and semantic draft counts to an import summary."""

    deleted: int = 0
    drafts: int = 0


class MetricDraft(BoundaryModel):
    """Retain unapproved dbt semantics outside the executable semantic layer."""

    unique_id: str
    description: str = ""
    definition: MetricDefinition | None = None
    raw: JsonDocument
    source_fingerprint: str | None = None
    status: Literal["draft", "confirmed"] = "draft"
    source_deleted: bool = False
