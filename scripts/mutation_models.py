# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Typed mutation targets and measured failures shared by local runners."""

from typing import Literal

from pydantic import Field

from datakeel.core.harness_eval import EvalCaseResult
from datakeel.core.models import BoundaryModel


class Mutation(BoundaryModel):
    """Replace exactly one production guard and require its relevant case to fail."""

    name: str
    path: str
    before: str
    after: str
    case: str
    runner: Literal["golden", "pytest"] = "golden"


class MutationResult(BoundaryModel):
    """Distinguish a detected behavior regression from a crashed evaluation process."""

    name: str
    killed: bool
    passed: int
    total: int
    failures: dict[str, list[str]] = Field(default_factory=dict)
    runner: Literal["golden", "pytest"] = "golden"
    target: str
    boundary_case: EvalCaseResult | None = None
    explanation_case: EvalCaseResult | None = None
    explanation_probe_exit: int | None = None
    validation_bypass: str | None = None


class TestMeasurement(BoundaryModel):
    """Keep actual test counts and assertion failures distinct from process or setup errors."""

    exit_code: int
    passed: int
    total: int
    failures: dict[str, list[str]]
