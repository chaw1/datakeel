# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Persist every tool dispatch, including rejected and interrupted requests."""

from datetime import UTC, datetime
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import select

from datakeel.core.errors import ConflictError, NotFoundError
from datakeel.core.models import JsonDocument, new_id, utcnow
from datakeel.ontology.tool_models import ToolInvocation, ToolInvocationStart, ToolOutcome
from datakeel.storage.database import Database
from datakeel.storage.tool_rows import ToolInvocationRow


def begin_invocation(db: Database, request: ToolInvocationStart) -> str:
    """Persist the attempt before dispatch so a process interruption remains visible."""
    with db.session() as session:
        db.lock_writes(session)
        if request.identifier and session.get(ToolInvocationRow, request.identifier) is not None:
            msg = "Tool call already has a durable invocation"
            raise ConflictError(msg)
        row = ToolInvocationRow(
            id=request.identifier or new_id(),
            name=request.name,
            actor=request.context.actor,
            agent_id=request.context.agent_id,
            session_id=request.context.session_id,
            parameters_summary={
                "digest": request.arguments_digest,
                "keys": request.argument_keys,
            },
            asset_refs=[ref.model_dump(mode="json") for ref in request.asset_refs],
        )
        session.add(row)
        session.commit()
        return row.id


def finish_invocation(db: Database, outcome: ToolOutcome, elapsed_ms: float) -> None:
    """Complete a span with the extracted assets and observed result status."""
    with db.session() as session:
        db.lock_writes(session)
        row = session.get(ToolInvocationRow, outcome.invocation_id)
        if row is None:
            msg = "Tool invocation was not started"
            raise NotFoundError(msg)
        row.status, row.error = outcome.status, outcome.error
        row.asset_refs = [ref.model_dump(mode="json") for ref in outcome.asset_refs]
        row.completed_at, row.elapsed_ms = utcnow().timestamp(), elapsed_ms
        row.outcome = outcome.model_dump(mode="json")
        session.commit()


def invocation_identity(session_id: str | None, call_id: str | None) -> str:
    """Bind a model tool correlation ID to one durable invocation in its conversation."""
    if call_id is None:
        return new_id()
    return str(uuid5(NAMESPACE_URL, f"datakeel:{session_id}:{call_id}"))


def replay_invocation(
    db: Database, identifier: str, name: str, arguments_digest: str
) -> ToolOutcome | None:
    """Reuse completed calls and refuse ambiguous or changed dispatches after interruption."""
    with db.session() as session:
        row = session.get(ToolInvocationRow, identifier)
        if row is None:
            return None
        if row.name != name or row.parameters_summary["digest"] != arguments_digest:
            msg = "Tool call ID is bound to different arguments"
            raise ConflictError(msg)
        if row.outcome is None:
            msg = "Tool call was interrupted before a durable outcome; inspect its audit"
            raise ConflictError(msg)
        return ToolOutcome.model_validate(row.outcome)


def _view(row: ToolInvocationRow) -> ToolInvocation:
    summary = JsonDocument.model_validate(row.parameters_summary)
    return ToolInvocation.model_validate(
        {
            "id": row.id,
            "name": row.name,
            "actor": row.actor,
            "agent_id": row.agent_id,
            "session_id": row.session_id,
            "arguments_digest": summary.root["digest"],
            "argument_keys": summary.root["keys"],
            "asset_refs": row.asset_refs,
            "status": row.status,
            "started_at": datetime.fromtimestamp(row.started_at, UTC),
            "completed_at": datetime.fromtimestamp(row.completed_at, UTC)
            if row.completed_at is not None
            else None,
            "elapsed_ms": row.elapsed_ms,
            "error": row.error,
        }
    )


def list_invocations(db: Database, session_id: str | None = None) -> list[ToolInvocation]:
    """Read invocation history in dispatch order, optionally scoped to a session."""
    with db.session() as session:
        statement = select(ToolInvocationRow).order_by(ToolInvocationRow.started_at)
        if session_id is not None:
            statement = statement.where(ToolInvocationRow.session_id == session_id)
        return [_view(row) for row in session.scalars(statement)]
