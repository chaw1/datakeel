# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Frozen quality monitoring histories, incidents, jobs and alert envelopes."""

from datetime import datetime
from typing import Literal

from pydantic import Field

from datakeel.core.dq_models import DqResult, DqRule
from datakeel.core.models import BoundaryModel

DqIssueStatus = Literal["open", "claimed", "recovered", "resolved"]


class DqRuleHistory(BoundaryModel):
    """Preserve each accepted rule mutation and its accountable actor."""

    rule_id: str
    revision: int
    operation: Literal["create", "update", "delete"]
    actor: str
    rule: DqRule
    occurred_at: datetime


class DqIssue(BoundaryModel):
    """Track a contiguous failure episode through human confirmation."""

    id: str
    rule_id: str
    status: DqIssueStatus
    assignee: str | None = None
    can_resolve: bool = False
    failures: int
    first_result_id: str
    last_result_id: str
    revision: int = Field(ge=1)
    created_at: datetime
    updated_at: datetime


class DqRun(BoundaryModel):
    """Expose one idempotent manual request or scheduled minute slot."""

    id: str
    rule_id: str
    rule_revision: int
    slot: str
    task_id: str
    state: str
    result_id: str | None = None
    error: str | None = None


class DqCompletion(BoundaryModel):
    """Publish a result only inside its task lease's terminal transaction."""

    run_id: str
    result: DqResult


class DqAlert(BoundaryModel):
    """Signed webhook payload, with no source credentials or sample contents."""

    event_id: str
    event_type: Literal["quality.failed", "quality.recovered"]
    issue: DqIssue
    rule_id: str
    rule_name: str
    severity: Literal["warn", "error"]
    result_id: str
    occurred_at: datetime


class DqWebhookDelivery(BoundaryModel):
    """Lease an immutable durable outbox payload without exposing secrets."""

    id: str
    owner: str
    body: str
    attempts: int
