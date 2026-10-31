# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Typed production workflow mutations and their declared authorization policies."""

from typing import Annotated, Literal

from pydantic import Field, model_validator

from datakeel.core.annotation_models import AnnotationRecord
from datakeel.core.models import BoundaryModel
from datakeel.core.prelabel_models import ConfidenceTier
from datakeel.core.production_models import (
    AssignmentStage,
    DispatchStrategy,
    SkillRequirement,
    WorkflowTier,
)


class ProductionActionParams(BoundaryModel):
    """Bind every production mutation to a client-generated replay identity."""

    request_id: str = Field(min_length=1, max_length=200)


class CreateProjectParams(ProductionActionParams):
    """Create a personal project by default against a published label version."""

    name: str = Field(min_length=1, max_length=200)
    dataset_id: str
    version_id: str
    label_set_id: str
    label_set_version: int = Field(default=1, ge=1)
    template_id: str | None = None
    workflow_tier: WorkflowTier = "personal"
    guidelines: str = ""
    lease_minutes: int = Field(default=10, ge=1, le=1440)
    dispatch_strategy: DispatchStrategy = "claim"
    skill_requirement: SkillRequirement | None = None
    max_active_tasks: int | None = Field(default=None, ge=1, le=10000)


class SplitPackagesParams(ProductionActionParams):
    """Partition every input sample once by stable count, directory or metadata grouping."""

    project_id: str
    package_size: int = Field(default=100, ge=1, le=10000)
    group_by: Literal["count", "directory", "metadata"] = "count"
    metadata_field: str | None = None


class ReworkTransfer(BoundaryModel):
    """State that a named assignment hands one rework round from its annotator to another."""

    task_id: str
    round: int = Field(ge=1)
    from_actor: str
    to_actor: str


class AssignTasksParams(ProductionActionParams):
    """Assign tasks to one named person, or match team skills and load deterministically.

    ``max_active_tasks`` may only lower the project's per-person limit. ``transfers`` is
    written by the server when the plan is prepared: every rework task this named assignment
    moves from its original annotator. Execution refuses a plan whose handovers changed.
    """

    task_ids: tuple[str, ...] = Field(min_length=1, max_length=10000)
    actor: str | None = Field(default=None, min_length=1)
    stage: AssignmentStage = "annotation"
    strategy: Literal["assign", "skill"] = "assign"
    candidates: tuple[str, ...] = Field(default=(), max_length=10000)
    skill_requirement: SkillRequirement | None = None
    max_active_tasks: int | None = Field(default=None, ge=1, le=10000)
    transfers: tuple[ReworkTransfer, ...] = Field(default=(), max_length=10000)

    @model_validator(mode="after")
    def require_target(self) -> "AssignTasksParams":
        """Name exactly one person for manual assignment and nobody for skill matching."""
        if self.strategy == "assign" and self.actor is None:
            message = "Named assignment requires actor"
            raise ValueError(message)
        if self.strategy == "skill" and self.actor is not None:
            message = "Skill dispatch selects people itself; omit actor"
            raise ValueError(message)
        return self


class ClaimTaskParams(ProductionActionParams):
    """Claim the next available task in a project or one of its packages."""

    project_id: str
    package_id: str | None = None
    stage: AssignmentStage = "annotation"


class TaskIdentityParams(ProductionActionParams):
    """Identify a task without requiring the caller to know its project."""

    task_id: str


class ReleaseTaskParams(TaskIdentityParams):
    """Relinquish an effective assignment while retaining every saved revision."""

    stage: AssignmentStage = "annotation"


class SaveRevisionParams(TaskIdentityParams):
    """Append an exact annotation only when its previous revision is still current."""

    previous_revision_id: str | None
    annotation: AnnotationRecord
    source: Literal["human", "model"] = "human"
    model_name: str | None = None
    model_version: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    object_confidences: tuple[Annotated[float, Field(ge=0, le=1)], ...] = ()
    confidence_tier: ConfidenceTier | None = None

    @model_validator(mode="after")
    def model_only_confidence(self) -> "SaveRevisionParams":
        """Keep per-object confidence and tiers as model provenance, never human input."""
        if self.source == "human" and (self.object_confidences or self.confidence_tier):
            message = "Only model revisions carry object confidences and confidence tiers"
            raise ValueError(message)
        return self


class SubmitTaskParams(TaskIdentityParams):
    """Submit the current revision for review or personal automatic approval."""


class ReviewTaskParams(TaskIdentityParams):
    """Approve or return an exact revision with explicit human issue statements."""

    revision_id: str
    decision: Literal["approve", "rework"]
    issues: tuple[str, ...] = ()


class ReopenTaskParams(TaskIdentityParams):
    """Reopen a task before the project has been finalized."""

    reason: str = Field(min_length=1)


class HeartbeatParams(TaskIdentityParams):
    """Renew the caller's own team-tier lease before it expires."""

    stage: AssignmentStage = "annotation"


class RevokeAssignmentParams(TaskIdentityParams):
    """Take an effective assignment back from any holder while keeping every revision."""

    stage: AssignmentStage = "annotation"
    reason: str = Field(min_length=1, max_length=2000)


class ConfigureProjectParams(ProductionActionParams):
    """Change team, tier-threshold and review-sampling settings; omitted fields stay unchanged.

    Lowering ``review_sample_rate`` below the current rate always requires a signed approval.
    """

    project_id: str
    lease_minutes: int | None = Field(default=None, ge=1, le=1440)
    dispatch_strategy: DispatchStrategy | None = None
    skill_requirement: SkillRequirement | None = None
    max_active_tasks: int | None = Field(default=None, ge=1, le=10000)
    confidence_high: float | None = Field(default=None, ge=0, le=1)
    confidence_low: float | None = Field(default=None, ge=0, le=1)
    review_sample_rate: float | None = Field(default=None, gt=0, le=1)
    clear: tuple[
        Literal["skill_requirement", "max_active_tasks", "confidence_thresholds"], ...
    ] = ()

    @model_validator(mode="after")
    def ordered_thresholds(self) -> "ConfigureProjectParams":
        """Keep the low threshold at or below the high threshold when both are given."""
        if (
            self.confidence_high is not None
            and self.confidence_low is not None
            and self.confidence_low > self.confidence_high
        ):
            message = "confidence_low must not exceed confidence_high"
            raise ValueError(message)
        return self


class UpgradeProjectParams(ProductionActionParams):
    """Upgrade the workflow tier in place, retaining all object identities and history."""

    project_id: str
    workflow_tier: WorkflowTier


PRODUCTION_PARAMETER_TYPES: dict[str, type[BoundaryModel]] = {
    "create_project": CreateProjectParams,
    "split_packages": SplitPackagesParams,
    "assign_tasks": AssignTasksParams,
    "claim_task": ClaimTaskParams,
    "release_task": ReleaseTaskParams,
    "save_revision": SaveRevisionParams,
    "submit_task": SubmitTaskParams,
    "review_task": ReviewTaskParams,
    "reopen_task": ReopenTaskParams,
    "upgrade_project": UpgradeProjectParams,
    "heartbeat": HeartbeatParams,
    "revoke_assignment": RevokeAssignmentParams,
    "configure_project": ConfigureProjectParams,
}

PRODUCTION_POLICIES: dict[str, tuple[str, bool, str]] = {
    "create_project": ("production:manage", False, "Create approved production project"),
    "split_packages": ("production:manage", True, "Partition project input reproducibly"),
    "assign_tasks": ("production:assign", True, "Assign exclusive production tasks"),
    "claim_task": ("production:claim", True, "Claim the next production task"),
    "release_task": ("production:claim", True, "Release an owned production assignment"),
    "save_revision": ("production:annotate", True, "Append an immutable annotation revision"),
    "submit_task": ("production:annotate", True, "Submit an owned production task"),
    "review_task": ("production:review", True, "Approve or rework a submitted revision"),
    "reopen_task": ("production:manage", True, "Reopen a task before project finalization"),
    "upgrade_project": ("production:manage", True, "Upgrade workflow without migrating data"),
    "heartbeat": ("production:claim", True, "Renew an owned team-tier assignment lease"),
    "revoke_assignment": ("production:assign", True, "Reclaim an assignment, keeping revisions"),
    "configure_project": ("production:manage", True, "Configure team leases, dispatch and load"),
}
