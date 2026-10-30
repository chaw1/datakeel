# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Read-only workbench projections of version-pinned production facts."""

from datetime import datetime
from typing import Literal

from pydantic import Field

from datakeel.core.annotation_models import AnnotationQAResult
from datakeel.core.identity_models import EffectiveScopes
from datakeel.core.models import BoundaryModel
from datakeel.core.production_catalog_models import LabelSet, ProductionTemplate
from datakeel.core.production_models import (
    AnnotationRevision,
    Assignment,
    AssignmentStage,
    ConfidenceDistribution,
    PrelabelAccuracy,
    ProductionProgress,
    ProductionTask,
    ProductionWorkload,
    Project,
    Review,
    SkillRequirement,
    TaskPackage,
)
from datakeel.core.production_team_models import DispatchSkip, LeaseRelease

WorkbenchView = Literal["all", "mine", "review"]


class WorkbenchProjectQuery(BoundaryModel):
    """Select a deterministic page inside an optional package and role projection."""

    limit: int = Field(default=200, ge=1, le=1000)
    cursor: str | None = None
    view: WorkbenchView = "all"
    package_id: str | None = None
    search: str | None = Field(
        default=None,
        min_length=1,
        max_length=200,
        description=(
            "Keep tasks whose sample's relative path or file name contains this text, "
            "ignoring case."
        ),
    )


class WorkbenchSampleName(BoundaryModel):
    """Name a task's sample by the relative path or file name recorded at import.

    Never a server path.
    """

    task_id: str
    sample_id: str
    name: str = Field(description="The sample's file name, without any directory.")
    path: str = Field(
        description=(
            "The path under the imported directory, such as `site-a/day-1/shelf.png`. "
            "Files imported on their own, and datasets imported before relative paths were "
            "recorded, show the file name. Server paths and object keys are never returned."
        )
    )


class WorkbenchTaskSampleQuery(BoundaryModel):
    """Select up to 500 tasks of one project whose sample names a page needs."""

    task_id: tuple[str, ...] = Field(default=(), max_length=500)


class WorkbenchTaskSamples(BoundaryModel):
    """Return sample names for the requested tasks that belong to the project."""

    items: tuple[WorkbenchSampleName, ...]


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
    template: ProductionTemplate | None = Field(
        description="The template version this project is locked to"
    )
    latest_template: ProductionTemplate | None = Field(
        default=None,
        description="The template's current revision; newer than template when an upgrade exists",
    )
    latest_label_set_version: int | None = Field(
        default=None, description="Newest published version of the project's label set"
    )
    effective_scopes: EffectiveScopes
    progress: ProductionProgress
    workload: ProductionWorkload
    confidence: ConfidenceDistribution
    agreement: AnnotationQAResult
    prelabel_accuracy: PrelabelAccuracy
    tasks: tuple[ProductionTask, ...]
    task_risks: tuple[WorkbenchTaskRisk, ...] = ()
    next_cursor: str | None = None
    task_samples: tuple[WorkbenchSampleName, ...] = ()


class WorkbenchSample(BoundaryModel):
    """Expose source content without returning a private path or object-store key."""

    id: str
    name: str
    path: str = Field(
        description=(
            "The path under the imported directory, such as `site-a/day-1/shelf.png`, or the "
            "file name when none was recorded. Never a server path or object key."
        )
    )
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


class WorkbenchLease(BoundaryModel):
    """Expose one running assignment's effective deadline and remaining time at the read."""

    assignment_id: str
    actor: str
    stage: AssignmentStage
    expires_at: datetime
    seconds_remaining: float
    enforced: bool


class WorkbenchTaskStatus(BoundaryModel):
    """Report a task's current state, holders, leases and releases without reading its source."""

    task: ProductionTask
    assignments: tuple[Assignment, ...]
    leases: tuple[WorkbenchLease, ...]
    releases: tuple[LeaseRelease, ...]
    observed_at: datetime


class SkillDispatchPreviewRequest(BoundaryModel):
    """Describe a skill dispatch exactly as assign_tasks would receive it, without writing."""

    task_ids: tuple[str, ...] = Field(min_length=1, max_length=10000)
    stage: AssignmentStage = "annotation"
    candidates: tuple[str, ...] = Field(default=(), max_length=10000)
    skill_requirement: SkillRequirement | None = None
    max_active_tasks: int | None = Field(default=None, ge=1, le=10000)


class DispatchPick(BoundaryModel):
    """Name the person a skill dispatch would give one task to."""

    task_id: str
    actor: str


class DispatchLoad(BoundaryModel):
    """Count one qualified person's current load and the tasks the dispatch would add."""

    actor: str
    current: int
    added: int


class SkillDispatchPreview(BoundaryModel):
    """Preview a skill dispatch with the same rules as execution: picks, loads and skips."""

    project_id: str
    stage: AssignmentStage
    skill_requirement: SkillRequirement
    max_active_tasks: int | None
    qualified: tuple[str, ...]
    picks: tuple[DispatchPick, ...]
    people: tuple[DispatchLoad, ...]
    unassigned: tuple[DispatchSkip, ...]


class AssignablePerson(BoundaryModel):
    """One active registered person who may receive one stage's work in a project."""

    actor: str
    display_name: str
    current: int = Field(ge=0)


class WorkbenchAssignees(BoundaryModel):
    """Who a manager can assign by name; earlier holders such as `local` need no account."""

    project_id: str
    stage: AssignmentStage
    people: tuple[AssignablePerson, ...]
