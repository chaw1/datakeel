# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Frozen field-standard contracts, profiles, recommendations and check results."""

import re
from decimal import Decimal
from typing import Literal, Self

from pydantic import ConfigDict, Field, computed_field, model_validator

from datakeel.core.metric_models import Scalar
from datakeel.core.models import BoundaryModel

type StandardValue = Scalar | Decimal

type StandardStatus = Literal["draft", "active", "deprecated"]
type Sensitivity = Literal["public", "internal", "confidential", "restricted"]
type ViolationRule = Literal[
    "type",
    "length",
    "precision",
    "code_list",
    "range",
    "pattern",
    "required",
    "unit",
    "sensitivity",
]


def standard_value_key(value: StandardValue) -> tuple[str, str]:
    """Match exact numeric reference values without conflating booleans or text codes."""
    if isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
        number = Decimal(str(value))
        normalized = format(number, "f")
        if "." in normalized:
            normalized = normalized.rstrip("0").rstrip(".")
        return "number", "0" if number == 0 else normalized
    return type(value).__name__, str(value)


class CodeEntry(BoundaryModel):
    """Assign bilingual business labels to one scalar reference value."""

    model_config = ConfigDict(allow_inf_nan=False)

    value: Scalar
    label_zh: str = Field(min_length=1)
    label_en: str = ""


class CodeList(BoundaryModel):
    """Version a reference code list independently of field standards."""

    code: str = Field(min_length=1)
    name: str = Field(min_length=1)
    entries: tuple[CodeEntry, ...] = ()
    version: int = Field(default=1, ge=1)
    status: StandardStatus = "draft"

    @model_validator(mode="after")
    def unique_values(self) -> Self:
        """Reject reference values whose typed identities collide."""
        values = [standard_value_key(entry.value) for entry in self.entries]
        if len(values) != len(set(values)):
            msg = "Duplicate code-list value"
            raise ValueError(msg)
        return self


class FieldStandard(BoundaryModel):
    """Describe the approved business meaning and permitted shape of a field."""

    code: str = Field(min_length=1)
    name_zh: str = Field(min_length=1)
    name_en: str = Field(min_length=1)
    description: str = Field(min_length=1)
    data_type: str = Field(min_length=1)
    length: int | None = Field(default=None, ge=1)
    precision: int | None = Field(default=None, ge=1)
    scale: int | None = Field(default=None, ge=0)
    code_list: str | None = None
    minimum: float | None = Field(default=None, allow_inf_nan=False)
    maximum: float | None = Field(default=None, allow_inf_nan=False)
    pattern: str | None = None
    unit: str | None = None
    required: bool = False
    sensitivity: Sensitivity = "internal"
    owner: str = ""
    version: int = Field(default=1, ge=1)
    status: StandardStatus = "draft"
    aliases: tuple[str, ...] = ()

    @model_validator(mode="after")
    def consistent_constraints(self) -> Self:
        """Validate numeric bounds, precision and the declared regular expression."""
        if self.minimum is not None and self.maximum is not None and self.minimum > self.maximum:
            msg = "Minimum must not exceed maximum"
            raise ValueError(msg)
        if self.scale is not None and self.precision is not None and self.scale > self.precision:
            msg = "Scale must not exceed precision"
            raise ValueError(msg)
        if self.pattern is not None:
            try:
                re.compile(self.pattern)
            except re.error as exc:
                msg = "Invalid field-standard regular expression"
                raise ValueError(msg) from exc
        return self


class StandardsContract(BoundaryModel):
    """Combine strict field and reference-data declarations in one YAML document."""

    standards: tuple[FieldStandard, ...] = ()
    code_lists: tuple[CodeList, ...] = ()

    @model_validator(mode="after")
    def unique_and_resolved(self) -> Self:
        """Reject duplicate codes and unknown reference-data dependencies."""
        for items in (self.standards, self.code_lists):
            codes = [item.code for item in items]
            if len(codes) != len(set(codes)):
                msg = "Duplicate standard or code-list code"
                raise ValueError(msg)
        known = {item.code for item in self.code_lists}
        if any(
            item.code_list is not None and item.code_list not in known for item in self.standards
        ):
            msg = "Field standard references an unknown code list"
            raise ValueError(msg)
        effective = {item.code for item in self.code_lists if item.status == "active"}
        if any(
            item.status == "active"
            and item.code_list is not None
            and item.code_list not in effective
            for item in self.standards
        ):
            msg = "Active field standard requires an active code list"
            raise ValueError(msg)
        return self


class ColumnProfile(BoundaryModel):
    """Carry bounded observations without retaining database handles or row objects."""

    column_id: str
    name: str
    data_type: str
    source_id: str = ""
    table_id: str = ""
    owner: str = ""
    values: tuple[StandardValue, ...] = ()
    row_count: int = Field(default=0, ge=0)
    null_count: int = Field(default=0, ge=0)
    truncated: bool = False
    unit: str | None = None
    sensitivity: Sensitivity | None = None
    length: int | None = Field(default=None, ge=1)
    precision: int | None = Field(default=None, ge=1)
    scale: int | None = Field(default=None, ge=0)


class MappingCandidate(BoundaryModel):
    """Explain one deterministic recommendation without confirming a mapping."""

    standard_code: str
    score: float = Field(ge=0, le=1)
    reasons: tuple[str, ...]


class MappingSuggestion(BoundaryModel):
    """Return at most three sufficiently supported candidates for one column."""

    column_id: str
    candidates: tuple[MappingCandidate, ...] = Field(default=(), max_length=3)


class ColumnMapping(BoundaryModel):
    """Represent a human-confirmed column-to-standard association."""

    column_id: str
    standard_code: str


class StandardViolation(BoundaryModel):
    """Count one failed constraint and expose only redacted representative values."""

    rule: ViolationRule
    count: int = Field(ge=1)
    samples: tuple[str, ...] = ()
    message: str


class ColumnCheck(BoundaryModel):
    """Report checks over observations; row_count defines the checked population."""

    column_id: str
    standard_code: str
    row_count: int = Field(ge=0)
    violations: tuple[StandardViolation, ...] = ()
    checked_rules: tuple[ViolationRule, ...] = ()
    skipped_rules: tuple[str, ...] = ()

    @computed_field
    @property
    def compliant(self) -> bool:
        """Return whether every evaluated constraint passed."""
        return not self.violations

    @computed_field
    @property
    def fully_checked(self) -> bool:
        """Return whether every declared constraint had sufficient evidence."""
        return not self.skipped_rules


class CoverageGroup(BoundaryModel):
    """Summarize coverage and mapped-column compliance within one metadata group."""

    key: str
    total_columns: int
    mapped_columns: int
    compliant_columns: int
    coverage: float
    compliance: float


class ViolationSummary(BoundaryModel):
    """Rank columns by observed violations without including raw sample values."""

    column_id: str
    standard_code: str
    violation_count: int
    rules: tuple[ViolationRule, ...]


class StandardsCoverage(BoundaryModel):
    """Expose global, database, table and owner coverage plus bounded violations."""

    overall: CoverageGroup
    sources: tuple[CoverageGroup, ...] = ()
    tables: tuple[CoverageGroup, ...] = ()
    owners: tuple[CoverageGroup, ...] = ()
    violation_top: tuple[ViolationSummary, ...] = ()
