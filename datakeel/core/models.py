# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Portable data models shared by execution, API, and projections."""

from collections.abc import ItemsView, KeysView
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, JsonValue, RootModel


def new_id() -> str:
    """Create a globally unique asset or event identity."""
    return str(uuid4())


def utcnow() -> datetime:
    """Return an aware UTC business timestamp."""
    return datetime.now(UTC)


class BoundaryModel(BaseModel):
    """Forbid unknown fields and attribute reassignment at module boundaries."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class Record(BoundaryModel):
    """Provide mapping access for legacy consumers of typed JSON responses.

    Any is restricted to this serialization compatibility boundary. New consumers
    should use model attributes; this adapter preserves the original public API.
    """

    def __getitem__(self, key: str) -> Any:  # noqa: ANN401  # Legacy JSON mapping boundary.
        """Read one JSON-compatible response field."""
        return self.model_dump(mode="json", by_alias=True)[key]

    def get(self, key: str, default: Any = None) -> Any:  # noqa: ANN401  # Legacy JSON boundary.
        """Read an optional JSON field with the legacy mapping convention."""
        return self.model_dump(mode="json", by_alias=True).get(key, default)

    def keys(self) -> KeysView[str]:
        """Expose serialized field names for legacy mapping consumers."""
        return self.model_dump(by_alias=True).keys()

    def items(self) -> ItemsView[str, Any]:
        """Expose serialized entries at the compatibility boundary."""
        return self.model_dump(mode="json", by_alias=True).items()


class AssetRef(Record):
    """Identify an asset in the sole authoritative storage namespace."""

    asset_type: str = "dataset"
    asset_id: str
    namespace: str = "default"
    version: str | None = None
    display_name: str | None = None


class FileItem(Record):
    """Describe one materialized file and its extensible JSON metadata."""

    id: str = Field(default_factory=new_id)
    path: str
    filename: str
    sha256: str = ""
    size: int = 0
    modality: str = "unknown"
    metadata: dict[str, Any] = Field(default_factory=dict)


class LineageEvent(Record):
    """Record an immutable attributed transformation or failure."""

    event_id: str = Field(default_factory=new_id)
    idempotency_key: str
    event_type: str = "TRANSFORM"
    inputs: list[AssetRef] = Field(default_factory=list[AssetRef])
    outputs: list[AssetRef] = Field(default_factory=list[AssetRef])
    operator: str
    on_behalf_of: str = "local-user"
    source_module: str = "pipeline"
    source_ref: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)
    run_state: str = "COMPLETED"
    occurred_at: datetime = Field(default_factory=utcnow)
    quality: dict[str, Any] = Field(default_factory=dict)


class JsonDocument(RootModel[dict[str, JsonValue]]):
    """Validate intentionally extensible JSON Schema and interchange documents.

    Root documents intentionally allow vocabulary-defined keys. Any return values
    below are restricted to the legacy JSON serialization compatibility boundary.
    """

    model_config = ConfigDict(frozen=True)

    def __getitem__(self, key: str) -> Any:  # noqa: ANN401  # Dynamic schema vocabulary boundary.
        """Read one dynamic vocabulary property."""
        return self.root[key]

    def get(self, key: str, default: Any = None) -> Any:  # noqa: ANN401  # Dynamic schema boundary.
        """Read an optional dynamic vocabulary property."""
        return self.root.get(key, default)

    def keys(self) -> set[str]:
        """Expose declared vocabulary keys for schema consumers."""
        return set(self.root)
