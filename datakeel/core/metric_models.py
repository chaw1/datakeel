# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Versioned semantic contracts and parameterized read-only query boundaries."""

from datetime import date
from typing import Literal, Self

from pydantic import Field, model_validator

from datakeel.core.models import BoundaryModel

type Scalar = str | int | float | bool | None


class MetricFilter(BoundaryModel):
    """Represent a typed comparison against a registered field."""

    column: str
    op: Literal["eq", "ne", "in", "gte", "lte"] = "eq"
    value: Scalar | list[Scalar]

    @model_validator(mode="after")
    def consistent_value(self) -> Self:
        """Keep membership lists distinct from scalar comparisons."""
        if (self.op == "in") != isinstance(self.value, list):
            msg = "The in operator requires a list; other operators require a scalar"
            raise ValueError(msg)
        return self


class Measure(BoundaryModel):
    """Bind one permitted aggregation to a catalog table and column."""

    table: str
    column: str
    aggregation: Literal["sum", "count", "avg", "min", "max", "count_distinct"]


class MetricTime(BoundaryModel):
    """Bind a metric to its registered temporal field and native precision."""

    column: str
    granularity: Literal["day", "month", "quarter", "year"] = "day"


class MetricDefinition(BoundaryModel):
    """Define the complete, immutable business meaning of one metric revision."""

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    english_name: str | None = Field(
        default=None, min_length=1, exclude_if=lambda value: value is None
    )
    synonyms: list[str] = Field(default_factory=list)
    description: str
    owner: str = Field(min_length=1)
    version: int = Field(default=1, ge=1)
    measure: Measure
    filters: list[MetricFilter] = Field(default_factory=list[MetricFilter])
    time: MetricTime
    dimensions: list[str] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)


class DimensionDefinition(BoundaryModel):
    """Bind a business dimension to a registered column and known values."""

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    english_name: str | None = Field(
        default=None, min_length=1, exclude_if=lambda value: value is None
    )
    synonyms: list[str] = Field(default_factory=list)
    column: str
    values: list[str] = Field(default_factory=list)


class TermTarget(BoundaryModel):
    """Identify a glossary term's registered semantic target."""

    kind: Literal["metric", "dimension", "column"]
    id: str


class TermDefinition(BoundaryModel):
    """Map a business term and synonyms to a typed semantic target."""

    term: str = Field(min_length=1)
    english_name: str | None = Field(
        default=None, min_length=1, exclude_if=lambda value: value is None
    )
    synonyms: list[str] = Field(default_factory=list)
    means: TermTarget


class OwnerDefinition(BoundaryModel):
    """Add optional display metadata to an owner referenced by its original name."""

    name: str = Field(min_length=1)
    english_name: str | None = Field(
        default=None, min_length=1, exclude_if=lambda value: value is None
    )


class SemanticLayer(BoundaryModel):
    """Load a complete collection of metrics, dimensions, and glossary entries."""

    metrics: list[MetricDefinition] = Field(default_factory=list[MetricDefinition])
    dimensions: list[DimensionDefinition] = Field(default_factory=list[DimensionDefinition])
    terms: list[TermDefinition] = Field(default_factory=list[TermDefinition])
    owners: list[OwnerDefinition] = Field(default_factory=list[OwnerDefinition])


class MetricCard(BoundaryModel):
    """Expose a metric revision and explicit reference resolution failures."""

    definition: MetricDefinition
    owner_english_name: str | None = Field(default=None, exclude_if=lambda value: value is None)
    status: Literal["resolved", "unresolved"] = "resolved"
    reasons: list[str] = Field(default_factory=list)


class TimeRange(BoundaryModel):
    """Select an inclusive start and exclusive end in the metric's date grain."""

    start: date
    end: date

    @model_validator(mode="after")
    def chronological(self) -> Self:
        """Reject empty or reversed time intervals."""
        if self.end <= self.start:
            msg = "Time range end must follow start"
            raise ValueError(msg)
        return self


class DimensionSlice(BoundaryModel):
    """Select a single dimension value by registered dimension identity."""

    dimension_id: str
    value: Scalar


class CompileRequest(BoundaryModel):
    """Request grouping, slices, date bounds, and typed additional filters."""

    dialect: Literal["sqlite", "postgres"] = "sqlite"
    slices: list[DimensionSlice] = Field(default_factory=list[DimensionSlice])
    group_by: list[str] = Field(default_factory=list)
    time_range: TimeRange | None = None
    filters: list[MetricFilter] = Field(default_factory=list[MetricFilter])


class CompiledQuery(BoundaryModel):
    """Carry compiler-generated SELECT SQL, bound parameters, and evidence."""

    metric_id: str
    metric_version: int
    source_id: str
    dialect: Literal["sqlite", "postgres"]
    sql: str
    parameters: dict[str, Scalar] = Field(default_factory=dict)
    tables: list[str]
    columns: list[str]


class QueryLimits(BoundaryModel):
    """Bound query execution time and returned rows at the execution boundary."""

    timeout_ms: int = Field(default=5000, ge=1, le=60000)
    max_rows: int = Field(default=1000, ge=1, le=10000)


class QueryResult(BoundaryModel):
    """Return ordered columns and scalar rows without exposing database handles."""

    columns: list[str]
    rows: list[list[Scalar]]
    truncated: bool = False


class MetricMutation(BoundaryModel):
    """Return the prior and new metric revisions with their authoritative event."""

    before: MetricCard
    after: MetricCard
    event_id: str


class ParameterBindings(BoundaryModel):
    """Collect named scalar binds during one compilation without untyped boundaries.

    The mapping mutates only inside a single compiler invocation while the model's
    field identity remains frozen; no instance is shared between requests.
    """

    values: dict[str, Scalar] = Field(default_factory=dict)
