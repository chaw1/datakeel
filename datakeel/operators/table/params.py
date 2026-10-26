# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Declare bounded strict parameters for deterministic table profiling."""

from typing import cast

from pydantic import Field, field_validator

from datakeel.operators.base import Params


class ProfileParams(Params):
    """Control null recognition, category inference and optional candidate scans."""

    null_values: tuple[str, ...] = ("", "null", "none", "nan", "n/a")
    enum_max_values: int = Field(default=20, ge=1, le=1000)
    enum_max_ratio: float = Field(default=0.2, ge=0, le=1)
    top_values_limit: int = Field(default=5, ge=1, le=20)
    detect_pii: bool = Field(
        default=True,
        description="Report PII findings; contact distribution values are always withheld",
    )
    detect_foreign_keys: bool = True

    @field_validator("null_values", mode="before")
    @classmethod
    def json_null_values(cls, value: object) -> object:
        """Accept JSON arrays as immutable tuples without coercing their items."""
        return tuple(cast("list[object]", value)) if isinstance(value, list) else value
