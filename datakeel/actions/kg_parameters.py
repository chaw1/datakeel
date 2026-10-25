# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Freeze explicit graph extraction scope and per-run budget limits."""

from decimal import Decimal
from typing import Literal

from pydantic import Field, field_validator

from datakeel.core.kg_execution import KGPrepared
from datakeel.core.models import BoundaryModel


class RunKGExtractionParams(BoundaryModel):
    """Schedule extraction of one immutable dataset version after impact preparation."""

    dataset_id: str = Field(min_length=1)
    version_id: str = Field(min_length=1)
    schema_id: str = "business-knowledge"
    profile_id: str = "replay-demo"
    file_ids: tuple[str, ...] = ()
    transcription_profile_id: str = "replay-image-demo"
    mode_overrides: dict[str, Literal["ocr", "vlm"]] = Field(default_factory=dict)
    budget_tokens: int = Field(default=250000, ge=0)
    max_cost_usd: Decimal = Field(default=Decimal(5), ge=0, allow_inf_nan=False)
    prepared: KGPrepared | None = None

    @field_validator("file_ids")
    @classmethod
    def canonical_files(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        """Make duplicate and reordered selections bind the same intent."""
        return tuple(sorted(set(values)))
