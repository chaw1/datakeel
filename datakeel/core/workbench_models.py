# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Read-only workbench projections of version-pinned production facts."""

from typing import Literal

from pydantic import Field

from datakeel.core.annotation_models import AnnotationQAResult
from datakeel.core.identity_models import EffectiveScopes
from datakeel.core.models import BoundaryModel
from datakeel.core.production_catalog_models import LabelSet, ProductionTemplate
from datakeel.core.production_models import (
    AnnotationRevision,
    Assignment,
    ConfidenceDistribution,
    PrelabelAccuracy,
    ProductionProgress,
    ProductionTask,
    ProductionWorkload,
    Project,
    Review,
    TaskPackage,
)

WorkbenchView = Literal["all", "mine", "review"]


class WorkbenchProjectQuery(BoundaryModel):
    """Select a deterministic page inside an optional package and role projection."""

    limit: int = Field(default=200, ge=1, le=1000)
    cursor: str | None = None
    view: WorkbenchView = "all"
    package_id: str | None = None


class WorkbenchTaskRisk(BoundaryModel):
    """Measure the current human annotation's content difference from its latest model draft."""

    task_id: str
    prelabel_difference: float | None = Field(default=None, ge=0, le=1)
    model_confidence: float | None = Field(default=None, ge=0, le=1)


class WorkbenchIndex(BoundaryModel):
    """List only readable projects and the caller's actual global server identity."""

    actor: str
    zero_users: bool
    effective_scopes: EffectiveScopes
    projects: tuple[Project, ...]


class WorkbenchProject(BoundaryModel):
    """Reuse production facts and measurements for role-specific workbench pages."""

    project: Project
    packages: tuple[TaskPackage, ...]
    label_set: LabelSet
    template: ProductionTemplate | None
    effective_scopes: EffectiveScopes
    progress: ProductionProgress
    workload: ProductionWorkload
    confidence: ConfidenceDistribution
    agreement: AnnotationQAResult
    prelabel_accuracy: PrelabelAccuracy
    tasks: tuple[ProductionTask, ...]
    task_risks: tuple[WorkbenchTaskRisk, ...] = ()
    next_cursor: str | None = None


class WorkbenchSample(BoundaryModel):
    """Expose source content without returning a private path or object-store key."""

    id: str
    name: str
    media_type: str
    text: str | None = None
    image_width: int | None = None
    image_height: int | None = None
    content_url: str
    thumbnail_url: str | None = None


class WorkbenchTask(BoundaryModel):
    """Return one sample and its exact append-only revision and review histories."""

    task: ProductionTask
    sample: WorkbenchSample
    revisions: tuple[AnnotationRevision, ...]
    reviews: tuple[Review, ...]
    assignments: tuple[Assignment, ...]
