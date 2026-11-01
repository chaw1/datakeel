# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Strongly typed, versioned skeleton topology shared by annotation and training contexts."""

from pydantic import Field, model_validator

from datakeel.core.models import BoundaryModel


class KeypointDefinition(BoundaryModel):
    """Define one stable, ordered skeleton point for annotation and COCO export."""

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    name_zh: str | None = None
    name_en: str | None = None
    required: bool = False


class SkeletonDefinition(BoundaryModel):
    """Define the single ordered point set and undirected edges of a template."""

    points: tuple[KeypointDefinition, ...] = Field(min_length=1, max_length=200)
    edges: tuple[tuple[str, str], ...] = Field(default=(), max_length=1000)

    @model_validator(mode="after")
    def valid_topology(self) -> "SkeletonDefinition":
        """Reject ambiguous point identities, missing endpoints, loops and duplicate edges."""
        identifiers = [point.id for point in self.points]
        if len(set(identifiers)) != len(identifiers):
            message = "Skeleton point identities must be unique"
            raise ValueError(message)
        known = set(identifiers)
        edges = [tuple(sorted(edge)) for edge in self.edges]
        if any(left == right or left not in known or right not in known for left, right in edges):
            message = "Skeleton edges require two distinct existing point identities"
            raise ValueError(message)
        if len(set(edges)) != len(edges):
            message = "Skeleton edges must be unique"
            raise ValueError(message)
        return self
