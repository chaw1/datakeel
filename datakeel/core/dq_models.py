# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Frozen quality-rule contracts and bounded execution observations."""

import math
import re
from datetime import datetime
from itertools import pairwise
from typing import Literal, Self

from pydantic import ConfigDict, Field, computed_field, field_validator, model_validator

from datakeel.core.dq_cron import validate_cron
from datakeel.core.metric_models import QueryLimits, Scalar
from datakeel.core.models import BoundaryModel, new_id, utcnow

type DqKind = Literal[
    "not_null",
    "unique",
    "range",
    "accepted_values",
    "regex",
    "referential_integrity",
    "freshness",
    "volume_change",
    "distribution_drift",
    "sql_assertion",
]


class DqTarget(BoundaryModel):
    """Identify a table in an existing catalog business source."""

    source_id: str = Field(min_length=1)
    table: str = Field(min_length=1)
    column: str | None = None
    schema_name: str | None = None


class DqParameters(BoundaryModel):
    """Type all optional rule parameters, with kind-specific invariants on the rule."""

    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)

    minimum: float | None = Field(default=None, allow_inf_nan=False)
    maximum: float | None = Field(default=None, allow_inf_nan=False)
    values: tuple[Scalar, ...] = ()
    pattern: str | None = Field(default=None, max_length=500)
    reference_table: str | None = None
    reference_column: str | None = None
    reference_schema: str | None = None
    baseline_runs: int = Field(default=3, ge=1, le=100)
    statistic: Literal["mean", "stddev", "null_rate", "psi"] = "mean"
    bin_edges: tuple[float, ...] = (-100.0, 0.0, 10.0, 100.0, 1000.0)
    sql: str | None = Field(default=None, max_length=20000)
    bindings: dict[str, Scalar] = Field(default_factory=dict[str, Scalar])

    @field_validator("bin_edges")
    @classmethod
    def ordered_edges(cls, value: tuple[float, ...]) -> tuple[float, ...]:
        """Require stable nonempty ordered bins for comparable PSI observations."""
        if (
            not value
            or not all(math.isfinite(edge) for edge in value)
            or any(left >= right for left, right in pairwise(value))
        ):
            msg = "PSI bin edges must be strictly increasing"
            raise ValueError(msg)
        return value

    @field_validator("pattern")
    @classmethod
    def safe_pattern(cls, value: str | None) -> str | None:
        """Validate syntax before isolated deadline-bound regex evaluation."""
        if value is None:
            return None
        try:
            re.compile(value)
        except (re.error, OverflowError) as error:
            msg = "Invalid quality-rule regex"
            raise ValueError(msg) from error
        return value


class DqQueryLimits(QueryLimits):
    """Bound explicit quality scans independently from interactive metric result limits."""

    max_rows: int = Field(default=10000, ge=1, le=100000)


class DqRule(BoundaryModel):
    """Version a complete YAML or web quality rule and its execution limits."""

    id: str = Field(min_length=1, max_length=200, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$")
    name: str = Field(min_length=1, max_length=200)
    target: DqTarget
    kind: DqKind
    params: DqParameters = Field(default_factory=DqParameters)
    revision: int = Field(default=1, ge=1)
    severity: Literal["warn", "error"] = "error"
    threshold: float = Field(default=0, ge=0, allow_inf_nan=False)
    cron: str | None = None
    owner: str = Field(min_length=1, max_length=200)
    dataset_id: str | None = None
    timeout_ms: int = Field(default=5000, ge=1, le=60000)
    max_rows: int = Field(default=10000, ge=1, le=100000)
    enabled: bool = True

    @field_validator("cron")
    @classmethod
    def valid_schedule(cls, value: str | None) -> str | None:
        """Reject invalid schedules consistently for YAML, actions and web forms."""
        return validate_cron(value) if value is not None else None

    @model_validator(mode="after")
    def coherent_rule(self) -> Self:
        """Reject incomplete definitions before opening a source connection."""
        table_kinds = {"volume_change", "sql_assertion"}
        if self.kind not in table_kinds and not self.target.column:
            msg = "This rule requires a target column"
            raise ValueError(msg)
        self._validate_parameters()
        return self

    def _validate_parameters(self) -> None:
        required = {
            "regex": self.params.pattern is not None,
            "range": self.params.minimum is not None or self.params.maximum is not None,
            "accepted_values": bool(self.params.values or self.params.reference_table),
            "referential_integrity": bool(
                self.params.reference_table and self.params.reference_column
            ),
            "sql_assertion": bool(self.params.sql),
        }
        if not required.get(self.kind, True):
            msg = "Required quality-rule parameters are missing"
            raise ValueError(msg)
        if self.params.reference_table and not self.params.reference_column:
            msg = "Reference tables require a reference column"
            raise ValueError(msg)
        if (
            self.params.minimum is not None
            and self.params.maximum is not None
            and self.params.minimum > self.params.maximum
        ):
            msg = "Range minimum cannot exceed maximum"
            raise ValueError(msg)


class DqMetrics(BoundaryModel):
    """Retain non-sensitive aggregate values for historical baselines."""

    row_count: int = Field(default=0, ge=0)
    mean: float | None = Field(default=None, allow_inf_nan=False)
    stddev: float | None = Field(default=None, allow_inf_nan=False)
    null_rate: float = Field(default=0, ge=0, le=1, allow_inf_nan=False)
    histogram: tuple[float, ...] = ()
    bin_edges: tuple[float, ...] = ()


class DqSample(BoundaryModel):
    """Expose only row ordinal and a redacted marker, never business cell contents."""

    row_number: int = Field(ge=1)
    column: str | None = None
    value: Literal["[REDACTED]"] = "[REDACTED]"


class DqResult(BoundaryModel):
    """Record one immutable evaluation, including explicit non-verdict states."""

    id: str = Field(default_factory=new_id)
    rule_id: str
    rule_revision: int = Field(default=1, ge=1)
    status: Literal["passed", "failed", "baseline_insufficient", "error"]
    actual_value: float | None = Field(default=None, allow_inf_nan=False)
    threshold: float = Field(default=0, ge=0, allow_inf_nan=False)
    row_count: int = 0
    failed_count: int = 0
    samples: tuple[DqSample, ...] = ()
    metrics: DqMetrics = Field(default_factory=DqMetrics)
    started_at: datetime = Field(default_factory=utcnow)
    duration_ms: float = Field(default=0, ge=0, allow_inf_nan=False)
    message: str = ""

    @computed_field
    @property
    def passed(self) -> bool | None:
        """Distinguish measured verdicts from failures to obtain an observation."""
        return {"passed": True, "failed": False}.get(self.status)


class DqContract(BoundaryModel):
    """Load an atomic versioned collection of quality rules."""

    version: Literal[1] = 1
    rules: tuple[DqRule, ...]

    @model_validator(mode="after")
    def unique_rules(self) -> Self:
        """Keep identifiers unique within a single imported contract."""
        if len({rule.id for rule in self.rules}) != len(self.rules):
            msg = "Quality-rule identifiers must be unique"
            raise ValueError(msg)
        return self
