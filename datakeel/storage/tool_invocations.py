# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Persist every tool dispatch, including rejected and interrupted requests."""

from datetime import UTC, datetime

from sqlalchemy import select

from datakeel.core.errors import NotFoundError
from datakeel.core.models import JsonDocument, utcnow
from datakeel.ontology.tool_models import ToolInvocation, ToolInvocationStart, ToolOutcome
from datakeel.storage.database import Database
from datakeel.storage.tool_rows import ToolInvocationRow


def begin_invocation(db: Database, request: ToolInvocationStart) -> str:
    """Persist the attempt before dispatch so a process interruption remains visible."""
    with db.session() as session:
        row = ToolInvocationRow(
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
        row = session.get(ToolInvocationRow, outcome.invocation_id)
        if row is None:
            msg = "Tool invocation was not started"
            raise NotFoundError(msg)
        row.status, row.error = outcome.status, outcome.error
        row.asset_refs = [ref.model_dump(mode="json") for ref in outcome.asset_refs]
        row.completed_at, row.elapsed_ms = utcnow().timestamp(), elapsed_ms
        session.commit()


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
