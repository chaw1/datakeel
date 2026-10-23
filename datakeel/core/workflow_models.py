# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Portable durable workflow run, step, recovery and streaming contracts."""

from datetime import datetime
from typing import Literal

from pydantic import Field, JsonValue

from datakeel.core.models import BoundaryModel, JsonDocument, new_id

WorkflowStatus = Literal["PENDING", "RUNNING", "PAUSED", "SUCCEEDED", "FAILED", "INTERRUPTED"]
StepStatus = Literal["PENDING", "RUNNING", "PAUSED", "SUCCEEDED", "SKIPPED", "FAILED"]


class WorkflowStart(BoundaryModel):
    """Bind an explicit human start to validated inputs and a durable replay key."""

    inputs: JsonDocument = Field(default_factory=lambda: JsonDocument({}))
    idempotency_key: str = Field(min_length=1, max_length=200)


class WorkflowStep(BoundaryModel):
    """Expose one declared step's durable progress and JSON output."""

    id: str
    type: str
    status: StepStatus = "PENDING"
    output: JsonValue = None
    error: str | None = None
    plan_id: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None


class WorkflowRun(BoundaryModel):
    """Read a complete run without exposing persistence rows or checkpoint state."""

    id: str
    workflow_id: str
    status: WorkflowStatus
    inputs: JsonDocument
    steps: list[WorkflowStep]
    pending_plan_id: str | None = None
    error: str | None = None
    created_at: datetime
    updated_at: datetime


class WorkflowEvent(BoundaryModel):
    """Send complete snapshots so reconnecting clients can recover through GET."""

    id: str = Field(default_factory=new_id)
    event: Literal["run", "step", "done"]
    run: WorkflowRun
    step_id: str | None = None


class WorkflowAudit(BoundaryModel):
    """Retain recovery authorization and interruption reasons beyond checkpoints."""

    id: str
    run_id: str
    plan_id: str | None = None
    kind: Literal["RESUME_DENIED", "RESUME_AUTHORIZED", "INTERRUPTED"]
    reason: str
    created_at: datetime


class WorkflowRecord(BoundaryModel):
    """Freeze the original definition and request alongside its public projection."""

    run: WorkflowRun
    definition: JsonDocument
    request_digest: str


class WorkflowRecovery(BoundaryModel):
    """Represent one separate resume request, including its replayable completion."""

    run_id: str
    plan_id: str
    idempotency_key: str
    completed: bool = False


class WorkflowCreation(BoundaryModel):
    """Pass a checked definition and initial steps into one creation transaction."""

    workflow_id: str
    definition: JsonDocument
    request: WorkflowStart
    steps: list[WorkflowStep]
