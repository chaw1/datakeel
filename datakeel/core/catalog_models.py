# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Typed metadata snapshots shared by importers, semantics, and persistence."""

from typing import Literal

from pydantic import Field, computed_field

from datakeel.core.models import AssetRef, BoundaryModel, JsonDocument

CatalogKind = Literal["source", "table", "column", "metric", "dimension", "term", "owner"]
CatalogLinkKind = Literal[
    "contains", "derived", "measures", "sliced_by", "means", "owned_by", "references"
]
CatalogOperator = Literal["CATALOG_IMPORT", "METRIC_CHANGE", "TERM_CHANGE"]
CATALOG_KINDS: tuple[CatalogKind, ...] = (
    "source",
    "table",
    "column",
    "metric",
    "dimension",
    "term",
    "owner",
)


class CatalogObject(BoundaryModel):
    """Describe one stable metadata identity and its immutable snapshot attributes."""

    asset_ref: AssetRef
    name: str
    source_id: str | None = None
    schema_name: str | None = None
    table_id: str | None = None
    properties: JsonDocument = Field(default_factory=lambda: JsonDocument({}))
    revision: int = Field(default=1, ge=1)
    producer_event_id: str | None = None


class CatalogLink(BoundaryModel):
    """Declare one explicit relationship, without inferring a Cartesian product."""

    source: AssetRef
    target: AssetRef
    kind: CatalogLinkKind
    producer_event_id: str | None = None


class CatalogSnapshot(BoundaryModel):
    """Version the complete metadata inventory owned by a single import scope."""

    scope: str
    objects: tuple[CatalogObject, ...] = ()
    links: tuple[CatalogLink, ...] = ()


class CatalogQuery(BoundaryModel):
    """Bound catalog reads by kind, source, containing object, or name."""

    kind: CatalogKind | None = None
    source_id: str | None = None
    parent_id: str | None = None
    search: str | None = None
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=100, ge=1, le=1000)


class CatalogPage(BoundaryModel):
    """Return one stable catalog page and its full matching count."""

    items: tuple[CatalogObject, ...]
    total: int
    offset: int
    limit: int


class CatalogImportRequest(BoundaryModel):
    """Identify one explicitly authorized database or local file metadata source."""

    source_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    connection_url: str | None = None
    files: tuple[str, ...] = ()
    sql_files: tuple[str, ...] = ()
    schemas: tuple[str, ...] = ()


class SqlFailure(BoundaryModel):
    """Keep the SQL origin and actionable parsing reason in import statistics."""

    origin: str
    reason: str


class ImportReport(BoundaryModel):
    """Summarize a versioned import including unchanged replay and SQL failures."""

    object_count: int
    new: int = 0
    changed: int = 0
    unchanged: int = 0
    link_count: int = 0
    parse_failures: tuple[SqlFailure, ...] = ()
    event_id: str | None = None
    snapshot_version: int = 0

    @computed_field
    @property
    def failed_sql_count(self) -> int:
        """Count individually reported failed SQL statements."""
        return len(self.parse_failures)


class ImpactResult(BoundaryModel):
    """Return a bounded downstream dependency traversal and explicit edges."""

    asset_id: str
    objects: tuple[CatalogObject, ...]
    links: tuple[CatalogLink, ...]
    truncated: bool = False


class SourceProperties(BoundaryModel):
    """Retain the data connection used by the read-only query execution boundary."""

    connection_url: str | None = None
    dialect: str
    files: tuple[str, ...] = ()


class ForeignKey(BoundaryModel):
    """Name the reflected columns participating in one foreign key."""

    columns: tuple[str, ...]
    target_table: str
    target_columns: tuple[str, ...]


class TableProperties(BoundaryModel):
    """Preserve reflected table identity, constraints, comments, and view SQL."""

    columns: dict[str, str] = Field(default_factory=dict[str, str])
    is_view: bool = False
    comment: str | None = None
    primary_key: tuple[str, ...] = ()
    foreign_keys: tuple[ForeignKey, ...] = ()
    sql: str | None = None


class ColumnProperties(BoundaryModel):
    """Preserve reflected or inferred column type, nullability, and comments."""

    data_type: str
    nullable: bool = True
    primary_key: bool = False
    comment: str | None = None
    ordinal: int = Field(ge=0)


class CatalogRebuildResult(BoundaryModel):
    """Compare the normalized catalog before and after authoritative event replay."""

    before_hash: str
    after_hash: str
    matches: bool
    objects: int
    edges: int
    events: int


class CatalogTableDetail(BoundaryModel):
    """Collect a table's fields, semantic consumers, ownership, and direct relationships."""

    table: CatalogObject
    columns: tuple[CatalogObject, ...]
    metrics: tuple[CatalogObject, ...]
    owners: tuple[CatalogObject, ...]
    neighbors: ImpactResult
