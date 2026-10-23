# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Immutable declarative workflow contracts with explicit control-flow edges."""

from typing import Annotated, Literal

from pydantic import Field, JsonValue, field_validator

from datakeel.core.models import BoundaryModel, JsonDocument

Identity = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_-]{0,63}$")]
Comparison = Literal["eq", "ne", "lt", "lte", "gt", "gte", "in"]


class WorkflowInput(BoundaryModel):
    """Describe one form input and its deterministic default value."""

    type: Literal["string", "number", "integer", "boolean", "object", "array"]
    description: str = ""
    required: bool = True
    default: JsonValue = None


class WorkflowTriggers(BoundaryModel):
    """Declare multilingual routing vocabulary and auditable score thresholds."""

    keywords: list[list[str]] = Field(min_length=1)
    classification_keywords: list[str] = Field(default_factory=list[str])
    excluded_keywords: list[str] = Field(default_factory=list[str])
    excluded_prefixes: list[str] = Field(default_factory=list[str])
    excluded_groups: list[list[str]] = Field(default_factory=list[list[str]])
    threshold: float = Field(default=1, gt=0)
    margin: float = Field(default=1, gt=0)

    @field_validator("keywords", "excluded_groups")
    @classmethod
    def validate_groups(cls, groups: list[list[str]]) -> list[list[str]]:
        """Reject empty concepts so every declared conjunction requires real vocabulary."""
        if any(not group for group in groups):
            msg = "keyword groups must not be empty"
            raise ValueError(msg)
        for group in groups:
            cls.validate_terms(group)
        return groups

    @field_validator("classification_keywords", "excluded_keywords", "excluded_prefixes")
    @classmethod
    def validate_terms(cls, terms: list[str]) -> list[str]:
        """Require a nonempty literal on both sides of every synonym separator."""
        if any(not alternative.strip() for term in terms for alternative in term.split("|")):
            msg = "keyword alternatives must not be empty"
            raise ValueError(msg)
        return terms


class ToolStep(BoundaryModel):
    """Invoke a registered read or prepare and execute a reversible action."""

    id: Identity
    type: Literal["tool"]
    tool: str
    arguments: JsonDocument
    next: Identity


class ApprovalStep(BoundaryModel):
    """Prepare, pause, and execute one irreversible action after authorization."""

    id: Identity
    type: Literal["approval"]
    action: str
    arguments: JsonDocument
    next: Identity


class WaitStep(BoundaryModel):
    """Poll one queued task with an explicit bounded deadline."""

    id: Identity
    type: Literal["wait"]
    task_id: JsonValue
    timeout_seconds: float = Field(default=60, gt=0, le=3600)
    poll_interval: float = Field(default=0.25, gt=0, le=60)
    next: Identity


class BranchStep(BoundaryModel):
    """Choose an edge using a reference, an allowlisted comparator, and an operand."""

    id: Identity
    type: Literal["branch"]
    ref: str
    op: Comparison
    value: JsonValue
    then: Identity
    otherwise: Identity


class OutputStep(BoundaryModel):
    """Finish a path with a JSON template using only pure expressions."""

    id: Identity
    type: Literal["output"]
    value: JsonValue


Step = Annotated[
    ToolStep | ApprovalStep | WaitStep | BranchStep | OutputStep, Field(discriminator="type")
]


class WorkflowDefinition(BoundaryModel):
    """Bind input declarations, routing vocabulary, and an acyclic step graph."""

    id: Identity
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    inputs: dict[str, WorkflowInput]
    triggers: WorkflowTriggers
    entry: Identity
    steps: list[Step] = Field(min_length=1, max_length=100)
