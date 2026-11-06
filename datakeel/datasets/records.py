# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Detached facts returned by dataset publication."""

from pydantic import JsonValue

from datakeel.core.models import BoundaryModel, FileItem


class PublishedDataset(BoundaryModel):
    """Frozen import result after dataset, version and lineage writes have flushed."""

    id: str
    name: str
    created_at: float
    files: tuple[FileItem, ...]
    metadata_values: dict[str, JsonValue]
    quality_config: dict[str, JsonValue]
    template: dict[str, JsonValue] | None
    compliance: dict[str, JsonValue]


class DatasetSettings(BoundaryModel):
    """Small frozen governance facts without loading the original manifest."""

    id: str
    name: str
    created_at: float
    metadata_values: dict[str, JsonValue]
    quality_config: dict[str, JsonValue]
    template: dict[str, JsonValue] | None
    compliance: dict[str, JsonValue]
