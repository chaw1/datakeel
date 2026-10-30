# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Immutable production projects, assignments, revision history and derived progress."""

from datetime import datetime
from typing import Literal

from pydantic import Field

from datakeel.core.annotation_models import AnnotationRecord
from datakeel.core.image_orientation import CoordinateConversion
from datakeel.core.models import BoundaryModel

WorkflowTier = Literal["personal", "group", "team"]
DispatchStrategy = Literal["assign", "skill", "claim"]
AssignmentSource = Literal["assign", "skill", "claim", "preserved"]
TaskState = Literal["pending", "in_progress", "submitted", "in_review", "approved", "finalized"]
AssignmentStage = Literal["annotation", "review"]
TASK_STATES: tuple[TaskState, ...] = (
    "pending",
    "in_progress",
    "submitted",
    "in_review",
    "approved",
    "finalized",
)


class SkillRequirement(BoundaryModel):
    """Require a matching skill type and domain at or above a minimum level."""

    annotation_type: str = Field(min_length=1)
    domain: str = Field(min_length=1)
    min_level: int = Field(default=1, ge=1, le=10)


class Project(BoundaryModel):
    """Bind production to immutable input data and published annotation rules."""

    id: str
    name: str
    dataset_id: str
    version_id: str
    label_set_id: str
    label_set_version: int
    template_id: str | None = None
    template_version: int | None = Field(
        default=None,
        ge=1,
        description=(
            "Template revision this project is locked to; only a signed "
            "upgrade_project_template changes it. Null only before the template lock migration."
        ),
    )
    workflow_tier: WorkflowTier = "personal"
    guidelines: str = ""
    created_at: datetime
    finalized_version_id: str | None = None
    review_prompt_shown: bool = False
    lease_minutes: int = Field(default=10, ge=1, le=1440)
    dispatch_strategy: DispatchStrategy = "claim"
    skill_requirement: SkillRequirement | None = None
    max_active_tasks: int | None = Field(default=None, ge=1, le=10000)


class TaskPackage(BoundaryModel):
    """Describe a reproducible partition whose status comes from task counters."""

    id: str
    project_id: str
    name: str
    task_count: int
    split_rule: str = "count"
    created_at: datetime


class ProductionTask(BoundaryModel):
    """Track one sample, its immutable revision heads and explicit rework round."""

    id: str
    project_id: str
    package_id: str
    sample_id: str
    state: TaskState = "pending"
    round: int = 0
    priority: int = 0
    latest_revision_id: str | None = None
    approved_revision_id: str | None = None
    annotator_id: str | None = None
    confidence: float | None = None


class Assignment(BoundaryModel):
    """Identify an actor's exclusive effective assignment for one task stage."""

    id: str
    task_id: str
    actor: str
    stage: AssignmentStage
    lease_expires_at: datetime
    active: bool = True
    created_at: datetime
    dispatch: AssignmentSource | None = None
    ended_at: datetime | None = None
    end_reason: str | None = None


class AnnotationRevision(BoundaryModel):
    """Append one annotation and its precise human or model provenance forever.

    ``coordinate_conversion`` is set only on reads of a revision saved in the stored pixel
    frame (before v0.19) of an EXIF-oriented image, naming the transform applied on read.
    """

    id: str
    task_id: str
    previous_revision_id: str | None
    annotation: AnnotationRecord
    source: Literal["human", "model"] = "human"
    actor: str
    model_name: str | None = None
    model_version: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    created_at: datetime
    coordinate_conversion: CoordinateConversion | None = None


class Review(BoundaryModel):
    """Retain a human decision against an exact submitted revision and round."""

    id: str
    task_id: str
    revision_id: str
    decision: Literal["approve", "rework"]
    issues: tuple[str, ...] = ()
    actor: str
    round: int
    created_at: datetime


class StateCount(BoundaryModel):
    """Expose one incrementally maintained state counter."""

    state: TaskState
    count: int = 0


class ProductionProgress(BoundaryModel):
    """Project current counters and repeatedly reworked tasks without counting all tasks."""

    project_id: str
    package_id: str | None = None
    total: int
    counts: tuple[StateCount, ...]
    status: str
    rework_task_ids: tuple[str, ...] = ()


class AnnotatorWorkload(BoundaryModel):
    """Report distinct handled tasks, submissions and human rework decisions."""

    actor: str
    assigned: int
    completed: int
    rework_count: int
    review_count: int
    rework_rate: float


class ProductionWorkload(BoundaryModel):
    """Contain exact workload and rework measurements for one project."""

    project_id: str
    annotators: tuple[AnnotatorWorkload, ...]


class ConfidenceBucket(BoundaryModel):
    """Count model revisions in a half-open bucket, with 1 included in the last."""

    lower: float
    upper: float
    count: int


class ConfidenceDistribution(BoundaryModel):
    """Count all model-source revision confidence observations for a project."""

    project_id: str
    total: int
    buckets: tuple[ConfidenceBucket, ...]


class PrelabelAccuracy(BoundaryModel):
    """Report exact model-draft agreement only against approved human reference revisions."""

    project_id: str
    assessed_tasks: int = Field(ge=0)
    exact_match_tasks: int = Field(ge=0)
    exact_match_rate: float | None = Field(default=None, ge=0, le=1)
