# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Frozen custom-code submissions, approved versions, and execution audit views."""

import re
from datetime import datetime
from typing import Literal

from pydantic import Field

from datakeel.core.errors import ValidationError
from datakeel.core.models import BoundaryModel, JsonDocument

CUSTOM_REFERENCE = re.compile(r"^custom\.([a-z][a-z0-9_-]{0,63})@([0-9a-f]{64})$")


class StaticCheck(BoundaryModel):
    """Display advisory source findings without treating them as containment."""

    line: int = Field(ge=1)
    column: int = Field(ge=0)
    code: str
    message: str


class CustomOperatorSubmission(BoundaryModel):
    """Accept one complete Python source file with schemas declared as literals."""

    name: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,63}$")
    code: str = Field(min_length=1, max_length=65536)
    modality: Literal["any", "text", "image"] = "any"


class SubmitCustomOperatorParams(CustomOperatorSubmission):
    """Freeze server-derived review material into the existing signed action plan."""

    code_hash: str = ""
    parameter_schema: JsonDocument | None = None
    metadata_schema: JsonDocument | None = None
    static_checks: tuple[StaticCheck, ...] = ()


class CustomOperatorVersion(CustomOperatorSubmission):
    """Identify an approved source version by its complete content digest."""

    id: str
    code_hash: str
    parameter_schema: JsonDocument
    metadata_schema: JsonDocument
    static_checks: tuple[StaticCheck, ...]
    plan_id: str
    approved_by: str
    approved_at: datetime


class CustomOperatorRun(BoundaryModel):
    """Keep immutable execution attribution for successful and failed attempts."""

    id: str
    operator: str
    code_hash: str
    image_digest: str
    backend: Literal["container", "subprocess"] = "container"
    params_digest: str
    task_id: str
    shard_id: str
    node_id: str
    attempt_id: str
    created_at: datetime
    completed_at: datetime
    success: bool
    exit_reason: str
    resources: JsonDocument
    output_count: int = Field(ge=0)


def custom_reference(value: str) -> tuple[str, str]:
    """Require an immutable custom operator name and SHA-256 reference."""
    match = CUSTOM_REFERENCE.fullmatch(value)
    if match is None:
        msg = "Custom operator reference must be custom.<name>@<sha256>"
        raise ValidationError(msg)
    return match.group(1), match.group(2)
