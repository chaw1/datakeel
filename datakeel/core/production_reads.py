# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Read-only production queries shared by HTTP, command line and tool adapters."""

from typing import Literal

from pydantic import Field

from datakeel.core.models import BoundaryModel
from datakeel.core.production_catalog_models import LabelMigration

ProductionKind = Literal[
    "user",
    "team",
    "role",
    "skill",
    "label_set",
    "template",
    "project",
    "task_package",
    "production_task",
    "assignment",
    "annotation_revision",
    "review",
    "model",
    "prelabel_run",
]


class ProjectReadParams(BoundaryModel):
    """Read exact statistics from one production project."""

    project_id: str = Field(min_length=1)


class PackageReadParams(ProjectReadParams):
    """Read task counters for a package belonging to the selected project."""

    package_id: str = Field(min_length=1)


class NextTaskParams(ProjectReadParams):
    """Find the caller's next eligible annotation without creating an assignment."""

    package_id: str | None = None


class LabelSetDiffParams(BoundaryModel):
    """Compare exact versions of one vocabulary and count affected current annotations."""

    label_set_id: str = Field(min_length=1)
    before_version: int = Field(ge=1)
    after_version: int = Field(ge=1)


class ProductionObjectFilters(BoundaryModel):
    """Bound production object reads by identity, parent and result count."""

    object_id: str | None = None
    project_id: str | None = None
    task_id: str | None = None
    version: int | None = Field(default=None, ge=1)
    limit: int = Field(default=100, ge=1, le=10000)


class ProductionObjectQuery(ProductionObjectFilters):
    """Select an ontology family in addition to its bounded fact filters."""

    kind: ProductionKind


class LabelSetDifference(BoundaryModel):
    """Report explicit migrations and exact instance and revision impact counts."""

    label_set_id: str
    before_version: int
    after_version: int
    added: tuple[str, ...]
    removed: tuple[str, ...]
    renamed: tuple[str, ...]
    affected_annotations: int
    affected_revisions: int
    migration: tuple[LabelMigration, ...]
