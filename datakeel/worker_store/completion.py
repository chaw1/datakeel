# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Frozen completion contracts; transaction binding is private composition wiring."""

from typing import Literal, Protocol

from datakeel.core.datasheet_execution import DatasheetCompletion
from datakeel.core.dq_monitor import DqCompletion
from datakeel.core.evidence_execution import PendingExtraction
from datakeel.core.kg_execution import KGCompletion
from datakeel.core.models import BoundaryModel

CompletionPayload = (
    tuple[PendingExtraction, ...] | KGCompletion | DqCompletion | DatasheetCompletion
)


class CompletionRequest(BoundaryModel):
    """Describe fenced publication or a terminal transition without mutable storage objects."""

    task_id: str
    dataset_id: str
    created_at: float
    phase: Literal["publish", "COMPLETED", "FAILED", "CANCELLED"] = "publish"
    error: str | None = None
    kg_run_id: str | None = None
    dq_run_id: str | None = None
    datasheet_job_id: str | None = None
    payload: CompletionPayload = ()


class CompletionResult(BoundaryModel):
    """Return only the existing terminal attribution and version-publication policy."""

    operator: str
    display_name: str = "Pipeline run"
    publish_version: bool = False


class TaskCompletionPort(Protocol):
    """Flush domain changes in the caller's bound transaction, without committing it."""

    def complete(self, request: CompletionRequest) -> CompletionResult:
        """Reject ambiguous routing and publish once behind the caller's lease fence."""
        ...
