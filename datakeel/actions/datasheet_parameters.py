# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Typed requests for controlled datasheet generation and publication."""

from typing import Literal, Self

from pydantic import Field, JsonValue, field_validator, model_validator

from datakeel.core.datasheet_execution import DatasheetPrepared
from datakeel.core.datasheet_models import DatasheetLanguage
from datakeel.core.harness_models import BudgetLimits
from datakeel.core.model_parameters import request_parameter_valid
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
    request_parameters: dict[str, JsonValue] = Field(default_factory=dict)

    @field_validator("request_parameters")
    @classmethod
    def validate_parameters(cls, values: dict[str, JsonValue]) -> dict[str, JsonValue]:
        """Accept the transcription profile's typed controls; chat endpoints have no num_ctx."""
        for name, value in values.items():
            if name == "num_ctx" or not request_parameter_valid(name, value):
                message = "request_parameters: unsupported parameter name or value"
                raise ValueError(message)
        return values

    @model_validator(mode="after")
    def validate_destination(self) -> Self:
        """Send request parameters only to an OpenAI-compatible model endpoint."""
        if self.request_parameters and (self.mode != "model" or self.provider != "openai"):
            message = "request_parameters require mode model with the openai provider"
            raise ValueError(message)
        return self


class GenerateDatasheetParams(GenerateDatasheetRequest):
    """Freeze server-derived facts before the action can be authorized."""

    dataset_id: str = Field(min_length=1)
    prepared: DatasheetPrepared | None = None


class PublishDatasheetParams(BoundaryModel):
    """Identify one checked immutable draft for explicit local approval."""

    dataset_id: str = Field(min_length=1)
    document_id: str = Field(min_length=1)
