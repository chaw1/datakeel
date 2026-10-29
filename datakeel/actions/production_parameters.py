# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Typed production workflow mutations and their declared authorization policies."""

from typing import Literal

from pydantic import Field

from datakeel.core.annotation_models import AnnotationRecord
from datakeel.core.models import BoundaryModel
from datakeel.core.production_models import AssignmentStage, WorkflowTier


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


class SplitPackagesParams(ProductionActionParams):
    """Partition every input sample once by stable count, directory or metadata grouping."""

    project_id: str
    package_size: int = Field(default=100, ge=1, le=10000)
    group_by: Literal["count", "directory", "metadata"] = "count"
    metadata_field: str | None = None


class AssignTasksParams(ProductionActionParams):
    """Assign named tasks to one person without skill matching in this phase."""

    task_ids: tuple[str, ...] = Field(min_length=1, max_length=10000)
    actor: str = Field(min_length=1)
    stage: AssignmentStage = "annotation"


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
}
