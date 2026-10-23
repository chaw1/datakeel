# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Run deterministic response processes with exact post-commit SIGKILL boundaries."""

from __future__ import annotations

import os
import signal
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Literal

import pytest
from pydantic import Field
from sqlalchemy import event

from datakeel.agent.providers import FakeProvider
from datakeel.agent.service import resume_conversation, send_message
from datakeel.core.agent_models import MessageInput, ModelResponse, ResumeInput, ToolCall
from datakeel.core.models import BoundaryModel, JsonDocument
from datakeel.runtime import graph as graph_module
from datakeel.runtime.saver import SQLAlchemySaver
from datakeel.storage.database import Database

if TYPE_CHECKING:
    from collections.abc import Sequence

    from langchain_core.runnables import RunnableConfig
    from sqlalchemy.engine.interfaces import DBAPIConnection
    from sqlalchemy.pool import ConnectionPoolEntry

    from datakeel.ontology.tool_models import ToolOutcome


class ProcessRequest(BoundaryModel):
    """Bind the child exclusively to the parent's generated database and artifacts."""

    database_url: str
    schema_name: str | None = Field(default=None, pattern=r"^test_[0-9a-f]{32}$")
    conversation_id: str
    dataset_id: str
    phase: Literal["pause", "resume_commit", "resume"]
    plan_id: str = ""
    marker: Path
    result: Path


def action_script(dataset_id: str) -> list[ModelResponse]:
    """Use fixed model correlation IDs so a restart must reuse the original tool audit."""
    return [
        ModelResponse(
            tool_calls=[
                ToolCall(
                    id="discover-action",
                    name="tool_search",
                    arguments=JsonDocument({"query": "delete_files"}),
                )
            ]
        ),
        ModelResponse(
            tool_calls=[
                ToolCall(
                    id="delete-selection",
                    name="delete_files",
                    arguments=JsonDocument(
                        {"selection": {"dataset_id": dataset_id, "quality_max": 0}}
                    ),
                )
            ]
        ),
        ModelResponse(content="Completed with the existing receipt."),
    ]


def _database(request: ProcessRequest) -> Database:
    db = Database(request.database_url)
    if not db.sqlite:
        assert db.engine.url.host in ("localhost", "127.0.0.1")
        assert request.schema_name is not None

        @event.listens_for(db.engine, "connect")
        def set_schema(connection: DBAPIConnection, _record: ConnectionPoolEntry) -> None:
            cursor = connection.cursor()
            cursor.execute(f'SET search_path TO "{request.schema_name}"')
            connection.commit()
            cursor.close()

    return db


def _kill(request: ProcessRequest) -> None:
    request.marker.write_text(request.phase, encoding="utf-8")
    os.kill(os.getpid(), signal.SIGKILL)


def _install_fault(request: ProcessRequest, patch: pytest.MonkeyPatch) -> None:
    if request.phase == "pause":
        original_writes = SQLAlchemySaver.put_writes

        def writes(
            saver: SQLAlchemySaver,
            config: RunnableConfig,
            updates: Sequence[tuple[str, object]],
            task_id: str,
            task_path: str = "",
        ) -> None:
            original_writes(saver, config, updates, task_id, task_path)
            if any(channel == "__interrupt__" for channel, _ in updates):
                _kill(request)

        patch.setattr(SQLAlchemySaver, "put_writes", writes)
    elif request.phase == "resume_commit":
        original_execute = graph_module.execute_approved

        def execute(db: Database, plan_id: str) -> ToolOutcome:
            outcome = original_execute(db, plan_id)
            assert outcome.run is not None
            assert outcome.run.status == "SUCCEEDED"
            _kill(request)
            return outcome

        patch.setattr(graph_module, "execute_approved", execute)


def main() -> None:
    """Run one real service call, leaving durable state when the child is killed."""
    request = ProcessRequest.model_validate_json(Path(sys.argv[1]).read_text(encoding="utf-8"))
    db = _database(request)
    with pytest.MonkeyPatch.context() as patch:
        _install_fault(request, patch)
        if request.phase == "pause":
            events = list(
                send_message(
                    db,
                    request.conversation_id,
                    MessageInput(content="Delete selected empty files"),
                    provider=FakeProvider(action_script(request.dataset_id)),
                )
            )
        else:
            events = list(
                resume_conversation(
                    db,
                    request.conversation_id,
                    ResumeInput(plan_id=request.plan_id, idempotency_key="resume-after-crash"),
                    provider=FakeProvider(
                        [ModelResponse(content="Recovered from the stored receipt.")]
                    ),
                )
            )
        request.result.write_text(
            "\n".join(item.model_dump_json() for item in events),
            encoding="utf-8",
        )
    db.engine.dispose()


if __name__ == "__main__":
    main()
