# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Typed requests for controlled datasheet generation and publication."""

from typing import Literal

from pydantic import Field

from datakeel.core.datasheet_execution import DatasheetPrepared
from datakeel.core.datasheet_models import DatasheetLanguage
from datakeel.core.harness_models import BudgetLimits
from datakeel.core.models import BoundaryModel


class GenerateDatasheetRequest(BoundaryModel):
    """Choose a version, language and optional existing model configuration."""

    version_id: str = Field(min_length=1)
    language: DatasheetLanguage = "zh"
    mode: Literal["template", "model"] = "template"
    provider: Literal["fake", "openai", "anthropic"] = "fake"
    model: str = Field(default="fake-demo", min_length=1)
    budget: BudgetLimits = Field(default_factory=BudgetLimits)
    max_output_tokens: int = Field(default=4096, ge=1, le=16384)


class GenerateDatasheetParams(GenerateDatasheetRequest):
    """Freeze server-derived facts before the action can be authorized."""

    dataset_id: str = Field(min_length=1)
    prepared: DatasheetPrepared | None = None


class PublishDatasheetParams(BoundaryModel):
    """Identify one checked immutable draft for explicit local approval."""

    dataset_id: str = Field(min_length=1)
    document_id: str = Field(min_length=1)
