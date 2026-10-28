# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Read the documented dbt artifact fields while preserving extensible raw evidence."""

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator

from datakeel.core.models import JsonDocument

# Parse bookkeeping, not project metadata: dbt rewrites these on every fresh parse
# (CI checkout, dbt clean, a different --target-path) of otherwise unchanged code.
VOLATILE_RESOURCE_FIELDS = frozenset({"created_at", "compiled_path", "build_path", "root_path"})


def stable_resource(raw: JsonDocument) -> JsonDocument:
    """Keep a raw resource as evidence without the fields a reparse rewrites."""
    return JsonDocument(
        {key: value for key, value in raw.root.items() if key not in VOLATILE_RESOURCE_FIELDS}
    )


class ArtifactModel(BaseModel):
    """Accept dbt's evolving resource vocabulary and freeze the fields used by the adapter."""

    model_config = ConfigDict(extra="ignore", frozen=True)


class DbtMetadata(ArtifactModel):
    """Declare the artifact schema and SQL adapter dialect."""

    dbt_schema_version: str
    adapter_type: str | None = None


class DbtColumn(ArtifactModel):
    """Read documented column attributes from manifest or warehouse catalog entries."""

    name: str
    description: str = ""
    data_type: str | None = None
    type: str | None = None
    comment: str | None = None
    index: int = 0
    meta: dict[str, JsonValue] = Field(default_factory=dict[str, JsonValue])
    tags: tuple[str, ...] = ()


class DbtConfig(ArtifactModel):
    """Read resource ownership, materialization, and configured tags."""

    meta: dict[str, JsonValue] = Field(default_factory=dict[str, JsonValue])
    tags: tuple[str, ...] = ()
    materialized: str = "table"

    @field_validator("tags", mode="before")
    @classmethod
    def single_tag(cls, value: JsonValue) -> JsonValue:
        """Accept dbt's documented single-string tag configuration."""
        return [value] if isinstance(value, str) else value


class DbtDependencies(ArtifactModel):
    """Keep only resource dependencies, independently of macro dependencies."""

    nodes: tuple[str, ...] = ()


class DbtOwner(ArtifactModel):
    """Read the documented exposure owner shape."""

    name: str | None = None
    email: str | None = None


class DbtNode(ArtifactModel):
    """Read the common resource fields present in manifest versions ten to twelve."""

    unique_id: str
    name: str
    resource_type: str
    database: str | None = None
    schema_name: str = Field(default="main", alias="schema")
    alias: str | None = None
    identifier: str | None = None
    relation_name: str | None = None
    description: str = ""
    meta: dict[str, JsonValue] = Field(default_factory=dict[str, JsonValue])
    source_meta: dict[str, JsonValue] = Field(default_factory=dict[str, JsonValue])
    config: DbtConfig = Field(default_factory=DbtConfig)
    columns: dict[str, DbtColumn] = Field(default_factory=dict[str, DbtColumn])
    tags: tuple[str, ...] = ()
    depends_on: DbtDependencies = Field(default_factory=DbtDependencies)
    compiled_code: str | None = None
    compiled_sql: str | None = None
    owner: DbtOwner | None = None
    column_name: str | None = None


class DbtCatalogMetadata(ArtifactModel):
    """Read reflected warehouse relation attributes from catalog.json."""

    type: str = "table"
    comment: str | None = None
    owner: str | None = None


class DbtCatalogNode(ArtifactModel):
    """Bind warehouse fields to the matching manifest unique identity."""

    metadata: DbtCatalogMetadata = Field(default_factory=DbtCatalogMetadata)
    columns: dict[str, DbtColumn] = Field(default_factory=dict[str, DbtColumn])


class DbtUnitTest(ArtifactModel):
    """Read v12 unit-test identity and dependencies without requiring a physical schema."""

    unique_id: str
    name: str
    resource_type: str
    model: str
    depends_on: DbtDependencies = Field(default_factory=DbtDependencies)


class DbtManifest(ArtifactModel):
    """Decode supported resource collections from a versioned dbt manifest."""

    metadata: DbtMetadata
    nodes: dict[str, DbtNode] = Field(default_factory=dict[str, DbtNode])
    sources: dict[str, DbtNode] = Field(default_factory=dict[str, DbtNode])
    exposures: dict[str, DbtNode] = Field(default_factory=dict[str, DbtNode])
    unit_tests: dict[str, DbtUnitTest] = Field(default_factory=dict[str, DbtUnitTest])


class DbtCatalog(ArtifactModel):
    """Decode the optional warehouse reflection artifact."""

    nodes: dict[str, DbtCatalogNode] = Field(default_factory=dict[str, DbtCatalogNode])
    sources: dict[str, DbtCatalogNode] = Field(default_factory=dict[str, DbtCatalogNode])
