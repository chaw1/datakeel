# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Finite discriminated measurements for relative, human-reviewed vector candidates."""

from typing import Annotated, Literal

from pydantic import Field

from datakeel.core.models import AssetRef, BoundaryModel
from datakeel.core.vector_models import Digest, VectorMember


class CosineMeasurement(BoundaryModel):
    """Record direct cosine similarity and the independent candidate threshold."""

    type: Literal["cosine_duplicate"] = "cosine_duplicate"
    similarity: float = Field(ge=-1, le=1, allow_inf_nan=False)
    threshold: float = Field(ge=-1, le=1, allow_inf_nan=False)


class ClusterMeasurement(BoundaryModel):
    """Describe membership in a stable reference-only DBSCAN cluster."""

    type: Literal["cluster_config"] = "cluster_config"
    eps: float = Field(ge=0, le=2, allow_inf_nan=False)
    min_samples: int = Field(ge=1)
    config_hash: Digest
    role: Literal["core", "border"]
    members: tuple[AssetRef, ...] = Field(min_length=1)


class OutlierMeasurement(BoundaryModel):
    """Record DBSCAN noise without treating it as corruption."""

    type: Literal["outlier_config"] = "outlier_config"
    eps: float = Field(ge=0, le=2, allow_inf_nan=False)
    min_samples: int = Field(ge=1)
    config_hash: Digest


class CoverageMeasurement(BoundaryModel):
    """Measure a candidate only relative to the complete frozen reference closure."""

    type: Literal["coverage"] = "coverage"
    nearest: AssetRef
    similarity: float = Field(ge=-1, le=1, allow_inf_nan=False)
    threshold: float = Field(ge=-1, le=1, allow_inf_nan=False)
    reference_digest: Digest
    references: tuple[VectorMember, ...] = Field(min_length=1)


VectorMeasurement = Annotated[
    CosineMeasurement | ClusterMeasurement | OutlierMeasurement | CoverageMeasurement,
    Field(discriminator="type"),
]
