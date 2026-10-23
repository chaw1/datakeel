# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Bound metadata function parameters independently of frozen file selection."""

from typing import Literal

from pydantic import Field

from datakeel.core.models import BoundaryModel


class MetricListParams(BoundaryModel):
    """Filter metric cards with explicit pagination and optional resolution status."""

    search: str | None = None
    status: Literal["resolved", "unresolved"] | None = None
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=100, ge=1, le=1000)


class MetricParams(BoundaryModel):
    """Address one metric using its stable semantic identifier."""

    metric_id: str = Field(min_length=1)


class ImpactParams(BoundaryModel):
    """Request the bounded downstream impact of an explicitly identified asset."""

    asset_id: str = Field(min_length=1)
    max_nodes: int = Field(default=200, ge=1, le=1000)
