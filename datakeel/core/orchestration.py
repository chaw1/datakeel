# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Typed OpenLineage run events and explicit physical namespace mappings."""

from datetime import UTC, datetime
from typing import Literal
from urllib.parse import urlsplit, urlunsplit

from pydantic import AwareDatetime, ConfigDict, Field, field_validator

from datakeel.core.catalog_identity import catalog_id
from datakeel.core.models import BoundaryModel, JsonDocument


class OpenLineageNamespace(BoundaryModel):
    """Map a dataset namespace to an already known physical catalog source."""

    source_id: str = Field(min_length=1)
    database: str | None = None


class OpenLineageEntity(BoundaryModel):
    """Read standard extensible job/dataset entities, ignoring producer extensions."""

    model_config = ConfigDict(extra="ignore", frozen=True)
    namespace: str = Field(min_length=1)
    name: str = Field(min_length=1)
    facets: JsonDocument = Field(default_factory=lambda: JsonDocument({}))

    @field_validator("namespace")
    @classmethod
    def normalize_namespace(cls, value: str) -> str:
        """Normalize URI scheme, host and trailing slash without folding dataset names."""
        return normalized_namespace(value)


class OpenLineageDataset(OpenLineageEntity):
    """Preserve schema and run-specific facets on a dataset reference."""

    inputFacets: JsonDocument | None = None  # noqa: N815  # OpenLineage vocabulary.
    outputFacets: JsonDocument | None = None  # noqa: N815  # OpenLineage vocabulary.


class OpenLineageRun(BoundaryModel):
    """Read a standard run identity and its extensible facet document."""

    model_config = ConfigDict(extra="ignore", frozen=True)
    runId: str = Field(min_length=1)  # noqa: N815  # OpenLineage vocabulary.
    facets: JsonDocument = Field(default_factory=lambda: JsonDocument({}))


RunEventType = Literal["START", "RUNNING", "COMPLETE", "ABORT", "FAIL", "OTHER"]
TERMINAL_EVENTS = frozenset({"COMPLETE", "ABORT", "FAIL"})
_CONTAINER_SCHEMES = frozenset({"abfss", "abfs", "wasbs", "wasb"})


class OpenLineageRunEvent(BoundaryModel):
    """Accept standard run transitions with camel-case interchange fields.

    START/RUNNING are in progress; COMPLETE/ABORT/FAIL are terminal; OTHER only
    carries metadata and never changes an observed run state.

    OpenLineage permits producer extensions; unknown interchange properties are
    ignored while all metadata kept across internal boundaries remains typed.
    """

    model_config = ConfigDict(extra="ignore", frozen=True)
    eventType: RunEventType  # noqa: N815  # OpenLineage vocabulary.
    eventTime: AwareDatetime  # noqa: N815  # OpenLineage vocabulary.
    run: OpenLineageRun
    job: OpenLineageEntity
    inputs: tuple[OpenLineageDataset, ...] = ()
    outputs: tuple[OpenLineageDataset, ...] = ()
    producer: str = Field(min_length=1)
    schemaURL: str = Field(min_length=1)  # noqa: N815  # OpenLineage vocabulary.

    @field_validator("eventTime")
    @classmethod
    def normalize_time(cls, value: datetime) -> datetime:
        """Convert aware interchange timestamps to UTC business time."""
        return value.astimezone(UTC)


class OpenLineageReceipt(BoundaryModel):
    """Report durable insertion and the effective state after out-of-order delivery."""

    inserted: bool
    event_id: str
    job_id: str
    run_id: str
    state: RunEventType
    occurred_at: datetime


def normalized_namespace(value: str) -> str:
    """Canonicalize URI aliases while preserving case-sensitive path components."""
    value = value.strip()
    if not value:
        msg = "A namespace must not be blank"
        raise ValueError(msg)
    parts = urlsplit(value)
    if not parts.scheme or not parts.netloc:
        return value.rstrip("/")
    scheme = parts.scheme.lower()
    # Azure lake namespaces name the container before "@": abfss://{container}@{account}.
    container = parts.username if scheme in _CONTAINER_SCHEMES and parts.password is None else None
    if parts.password is not None or (parts.username and container is None):
        msg = "Namespace URIs must not contain credentials"
        raise ValueError(msg)
    host = (parts.hostname or "").lower()
    if ":" in host:
        host = f"[{host}]"
    port = parts.port
    if scheme == "postgresql":
        scheme = "postgres"
    defaults = {"postgres": 5432, "mysql": 3306, "http": 80, "https": 443}
    authority = f"{host}:{port}" if port and port != defaults.get(scheme) else host
    if container:
        authority = f"{container}@{authority}"
    return urlunsplit((scheme, authority, parts.path.rstrip("/"), parts.query, parts.fragment))


def openlineage_job_id(job: OpenLineageEntity) -> str:
    """Separate orchestration jobs from physical table identities."""
    return catalog_id("openlineage-job", job.namespace, job.name)
