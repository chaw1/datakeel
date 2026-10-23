# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Immutable DAG specifications and typed execution observations."""

from typing import Any, Literal, Self

from pydantic import ConfigDict, Field, model_validator

from datakeel.core.errors import ValidationError
from datakeel.core.models import Record
from datakeel.operators.base import Params


class ConditionParams(Params):
    """Select one branch using the inclusive input-count bounds."""

    min_count: int = Field(default=1, ge=0)
    max_count: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def bounds(self) -> Self:
        """Reject an inverted branch interval."""
        if self.max_count is not None and self.max_count < self.min_count:
            msg = "max_count must be at least min_count"
            raise ValidationError(msg)
        return self


class Node(Record):
    """Declare typed input slots and validated operator parameters."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    id: str = Field(pattern=r"^[a-zA-Z][a-zA-Z0-9_-]{0,63}$")
    kind: Literal["operator", "condition", "route"] = "operator"
    operator: str | None = None
    inputs: dict[str, str]
    # Any is confined to heterogeneous operator-parameter JSON; registry validates it.
    params: dict[str, Any] = Field(default_factory=dict)


class Pipeline(Record):
    """Describe an acyclic set of nodes and the published output slots."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    nodes: list[Node] = Field(min_length=1, max_length=100)
    outputs: list[str] = Field(min_length=1)
    max_workers: int = Field(default=4, ge=1, le=32)


class PipelineObservation(Record):
    """Transfer a terminal node observation to the transactional worker."""

    node_id: str
    operator: str
    params: dict[str, Any]
    input_count: int
    inputs: list[str]
    output_count: int
    outputs: list[str]
    quality: dict[str, Any]
    run_state: Literal["COMPLETED", "FAILED"]
