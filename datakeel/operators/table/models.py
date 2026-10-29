# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Frozen column summaries, relationship candidates and row-level findings."""

from typing import Literal

from pydantic import Field

from datakeel.core.models import Record
from datakeel.core.pii import PiiType

ColumnType = Literal[
    "empty",
    "boolean",
    "integer",
    "number",
    "amount",
    "date",
    "datetime",
    "identifier",
    "enum",
    "string",
]
PiiKind = PiiType


class ValueCount(Record):
    """Count an observed category without retaining suspected personal values."""

    value: str
    count: int = Field(ge=1)


class NumericSummary(Record):
    """Summarize finite numeric values with population standard deviation."""

    minimum: float
    maximum: float
    mean: float
    median: float
    standard_deviation: float
    first_quartile: float
    third_quartile: float


class DistributionSummary(Record):
    """Expose bounded category counts, numeric moments and value lengths."""

    numeric: NumericSummary | None = None
    top_values: tuple[ValueCount, ...] = ()
    minimum_length: int | None = None
    maximum_length: int | None = None


class ColumnProfile(Record):
    """Describe a column's inferred semantics and observed completeness."""

    name: str
    inferred_type: ColumnType
    null_count: int = Field(ge=0)
    null_rate: float = Field(ge=0, le=1)
    distinct_count: int = Field(ge=0)
    unique_rate: float = Field(ge=0, le=1)
    primary_key_candidate: bool
    pii_kinds: tuple[PiiKind, ...] = ()
    distribution: DistributionSummary


class ForeignKeyCandidate(Record):
    """Report a name-compatible inclusion dependency as a candidate only."""

    column: str
    referenced_file: str
    referenced_column: str
    matched_distinct_values: int = Field(ge=1)
    coverage: float = Field(ge=0, le=1)


class ProfileFinding(Record):
    """Anchor one profiling issue to a column and original source row numbers."""

    code: Literal["null_values", "suspected_pii", "mixed_types", "empty_table"]
    severity: Literal["warning", "error"] = "warning"
    column: str | None = None
    row_numbers: tuple[int, ...] = ()
    count: int = Field(ge=0)
    detail: str
    suggested_action: str


class TableProfile(Record):
    """Carry a deterministic typed table profile for metadata and reports."""

    row_count: int = Field(ge=0)
    column_count: int = Field(ge=0)
    columns: tuple[ColumnProfile, ...]
    foreign_keys: tuple[ForeignKeyCandidate, ...] = ()
    findings: tuple[ProfileFinding, ...] = ()
