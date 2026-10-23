# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Validated argument schemas for built-in read functions."""

from typing import Literal

from pydantic import Field

from datakeel.core.models import BoundaryModel


class ListDatasetsParams(BoundaryModel):
    """List local datasets, optionally limiting the number returned."""

    limit: int = Field(default=100, ge=1, le=1000)


class SearchFilesParams(BoundaryModel):
    """Search stored file evidence without reading raw object content."""

    dataset_id: str | None = None
    modality: str | None = None
    quality_min: float | None = Field(default=None, ge=0, le=100)
    quality_max: float | None = Field(default=None, ge=0, le=100)
    quarantined: bool | None = None
    path: str | None = None
    version_id: str | None = None
    limit: int = Field(default=100, ge=1, le=1000)


class DatasetParams(BoundaryModel):
    """Address a dataset by its authoritative asset identity."""

    dataset_id: str = Field(min_length=1)


class LineageParams(BoundaryModel):
    """Bound a directional lineage query around a known asset identity."""

    asset_id: str = Field(min_length=1)
    direction: Literal["both", "upstream", "downstream"] = "both"
    depth: int = Field(default=20, ge=0, le=100)


class TaskParams(BoundaryModel):
    """Address one durable task."""

    task_id: str = Field(min_length=1)


class EvidenceAssetParams(BoundaryModel):
    """Address a sample's evidence by its authoritative file identity."""

    asset_id: str = Field(min_length=1)
    version_id: str | None = Field(default=None, min_length=1)
