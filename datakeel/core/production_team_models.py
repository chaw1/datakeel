# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Team-tier lease, dispatch and package acceptance facts and read projections."""

from datetime import datetime
from typing import Literal

from pydantic import Field, model_validator

from datakeel.core.annotation_sampling import InspectionCheck, SamplingRequest
from datakeel.core.models import BoundaryModel
from datakeel.core.production_models import Assignment, AssignmentStage

PackageAcceptanceState = Literal["in_progress", "ready", "accepted", "rejected"]


class LeaseRelease(BoundaryModel):
    """Record the single release of one assignment by lease expiry or administrative reclaim."""

    assignment_id: str
    task_id: str
    project_id: str
    actor: str
    stage: AssignmentStage
    reason: Literal["expired", "revoked"]
    lease_expires_at: datetime
    released_at: datetime
    released_by: str
    note: str = ""


class LeaseReapResult(BoundaryModel):
    """Count expired leases released by one reaper pass and those left to a later pass."""

    released: int = 0
    skipped_locked: int = 0
    assignment_ids: tuple[str, ...] = ()


class LeaseView(BoundaryModel):
    """Expose an effective team lease with its remaining time at the read instant."""

    assignment: Assignment
    seconds_remaining: float


class LeaseStatus(BoundaryModel):
    """List live, soon-expiring, overdue and recently reclaimed leases for one project."""

    project_id: str
    observed_at: datetime
    expiring_within_seconds: int
    active: tuple[LeaseView, ...]
    expiring: tuple[LeaseView, ...]
    overdue: tuple[LeaseView, ...]
    reclaimed: tuple[LeaseRelease, ...]


class SkillWorkload(BoundaryModel):
    """Aggregate current and completed annotation work of everyone holding one skill."""

    skill_id: str
    name: str
    annotation_type: str
    domain: str
    level: int
    users: tuple[str, ...]
    active_assignments: int
    completed_tasks: int


class ProductionSkillWorkload(BoundaryModel):
    """Contain per-skill workload for one project, in stable skill identity order."""

    project_id: str
    skills: tuple[SkillWorkload, ...]


class DispatchSkip(BoundaryModel):
    """Explain why one requested task received no skill-matched assignment."""

    task_id: str
    reason: str


class PackageSamplingParams(BoundaryModel):
    """Choose P26 AQL or fixed-ratio sampling for one package inspection."""

    method: Literal["aql", "ratio"] = "aql"
    aql: float = Field(default=2.5, gt=0, le=10, allow_inf_nan=False)
    ratio: float | None = Field(default=None, gt=0, le=1, allow_inf_nan=False)
    acceptance_number: int | None = Field(default=None, ge=0)
    seed: int = Field(default=0, ge=0, le=4_294_967_295)

    @model_validator(mode="after")
    def validate_method(self) -> "PackageSamplingParams":
        """Apply exactly the P26 request rules so both sampling paths accept the same inputs."""
        self.sampling_request("package")
        return self

    def sampling_request(self, unit_scope: str) -> SamplingRequest:
        """Return the equivalent P26 request bound to a package rather than a batch."""
        return SamplingRequest(
            batch_id=unit_scope,
            method=self.method,
            aql=self.aql,
            ratio=self.ratio,
            acceptance_number=self.acceptance_number,
            seed=self.seed,
        )


class PackageSampling(BoundaryModel):
    """Reproduce the P26 plan over a package's approved samples."""

    lot_size: int
    sample_size: int
    sample_ids: tuple[str, ...]
    task_ids: tuple[str, ...]
    acceptance_number: int
    rejection_number: int
    code_letter: str | None = None
    effective_code_letter: str | None = None
    method: Literal["aql", "ratio"]
    aql: float | None = None
    ratio: float | None = None
    seed: int


class PackageInspection(BoundaryModel):
    """Archive one signed package decision and the exact approved revisions it covered."""

    id: str
    action_plan_id: str
    project_id: str
    package_id: str
    sampling: PackageSampling
    checks: tuple[InspectionCheck, ...]
    defective_count: int
    accepted: bool
    revision_digest: str
    returned_task_ids: tuple[str, ...] = ()
    actor: str
    created_at: datetime


class PackageAcceptance(BoundaryModel):
    """Report a package's acceptance state, a reproducible sample preview and its last decision."""

    project_id: str
    package_id: str
    status: PackageAcceptanceState
    total: int
    approved: int
    sampling: PackageSampling | None = None
    latest: PackageInspection | None = None
    inspections: int = 0
