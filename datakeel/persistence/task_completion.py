# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Explicit completion adapters bound to the queue owner's one writer session."""

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from datakeel.core.datasheet_execution import DatasheetCompletion
from datakeel.core.dq_monitor import DqCompletion
from datakeel.core.errors import ConflictError
from datakeel.core.kg_execution import KGCompletion
from datakeel.persistence.task_vector import validate_vector_completion
from datakeel.storage.datasheet_jobs import finish_failed as fail_datasheet
from datakeel.storage.datasheet_jobs import publish_completion as publish_datasheet
from datakeel.storage.dq_results import finish_failed as fail_dq
from datakeel.storage.dq_results import publish_completion as publish_dq
from datakeel.storage.evidence_store import record_extraction_in_session
from datakeel.storage.kg_publication import publish_completion as publish_kg
from datakeel.storage.kg_store import finish_failed as fail_kg
from datakeel.storage.vector_budget import recover_vectors
from datakeel.storage.vector_reports import has_vector_work
from datakeel.worker_store.completion import CompletionRequest, CompletionResult, ExpirationResult


class BoundTaskCompletion:
    """Wire existing handlers to one session; never own a commit or action receipt."""

    def __init__(self, session: Session) -> None:
        """Bind handlers only inside the owning queue transaction."""
        self._session = session

    def complete(self, request: CompletionRequest) -> CompletionResult:
        """Route by persisted association and checked payload, failing closed on mismatch."""
        associations = (request.kg_run_id, request.dq_run_id, request.datasheet_job_id)
        if sum(value is not None for value in associations) > 1 or any(
            value == "" for value in associations
        ):
            msg = "Task completion has ambiguous or empty associations"
            raise ConflictError(msg)
        if request.kg_run_id is not None:
            return self._kg(request)
        if request.dq_run_id is not None:
            return self._dq(request)
        if request.datasheet_job_id is not None:
            return self._datasheet(request)
        return self._pipeline(request)

    @staticmethod
    def _require_payload(
        request: CompletionRequest,
        *,
        matches: bool,
        message: str = "Task completion payload does not match its association",
    ) -> None:
        # Failure/cancel/reaper historically carry no product; success must carry its exact one.
        empty_failure = request.payload == () and (
            request.phase in {"FAILED", "CANCELLED"} or bool(request.error)
        )
        if not matches and not empty_failure:
            raise ConflictError(message)

    def _kg(self, request: CompletionRequest) -> CompletionResult:
        payload = request.payload
        self._require_payload(
            request,
            matches=isinstance(payload, KGCompletion) and payload.run.id == request.kg_run_id,
        )
        if request.phase == "publish" and isinstance(payload, KGCompletion):
            publish_kg(self._session, payload, request.task_id)
        elif request.phase in {"FAILED", "CANCELLED"}:
            fail_kg(self._session, request.kg_run_id or "", request.error or "Graph task cancelled")
        return CompletionResult(operator="kg.complete")

    def _dq(self, request: CompletionRequest) -> CompletionResult:
        payload = request.payload
        self._require_payload(
            request,
            matches=isinstance(payload, DqCompletion) and payload.run_id == request.dq_run_id,
        )
        if request.phase == "publish" and isinstance(payload, DqCompletion):
            publish_dq(self._session, payload, request.task_id)
        elif request.phase in {"FAILED", "CANCELLED"}:
            fail_dq(
                self._session,
                request.dq_run_id or "",
                request.error or "Quality task cancelled",
                cancelled=request.phase == "CANCELLED",
                started_at=datetime.fromtimestamp(request.created_at, UTC),
            )
        return CompletionResult(operator="dq.complete")

    def _datasheet(self, request: CompletionRequest) -> CompletionResult:
        payload = request.payload
        self._require_payload(
            request,
            matches=isinstance(payload, DatasheetCompletion)
            and payload.job_id == request.datasheet_job_id,
            message="Successful datasheet tasks require their exact checked completion",
        )
        if request.phase == "publish" and isinstance(payload, DatasheetCompletion):
            publish_datasheet(self._session, payload, request.task_id)
        elif request.phase in {"FAILED", "CANCELLED"}:
            fail_datasheet(
                self._session,
                request.datasheet_job_id or "",
                request.error or "Datasheet task cancelled",
                cancelled=request.phase == "CANCELLED",
            )
        return CompletionResult(operator="datasheet.complete", display_name="Datasheet generation")

    def _pipeline(self, request: CompletionRequest) -> CompletionResult:
        if not isinstance(request.payload, tuple):
            msg = "Task completion payload has no matching association"
            raise ConflictError(msg)
        discard = bool(request.error) and has_vector_work(
            self._session, request.task_id, request.pipeline
        )
        if request.phase == "publish":
            payload = validate_vector_completion(
                self._session, request, request.payload, request.error
            )
            for pending in payload:
                record_extraction_in_session(self._session, pending.event, pending.bundle)
        if discard:
            return CompletionResult(operator="pipeline.complete", discard_outputs=True)
        return CompletionResult(operator="pipeline.complete", publish_version=True)

    def expiration(self, request: CompletionRequest) -> ExpirationResult:
        """Never requeue a vector DAG or any task with durable vector attempts."""
        return ExpirationResult(
            error="vector_lease_expired_outcome_unknown"
            if has_vector_work(self._session, request.task_id, request.pipeline)
            else None
        )

    def recover(self, request: CompletionRequest) -> None:
        """Run after the queue has flushed terminal state and its outbox."""
        if request.phase in {"FAILED", "CANCELLED"}:
            recover_vectors(self._session, request.task_id)
