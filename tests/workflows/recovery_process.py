# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Execute real workflow processes with post-interrupt and post-action SIGKILL faults."""

from __future__ import annotations

import os
import signal
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Literal

import pytest
from pydantic import Field
from sqlalchemy import event

from datakeel.core.agent_models import ResumeInput
from datakeel.core.models import BoundaryModel, JsonDocument
from datakeel.core.workflow_models import WorkflowStart
from datakeel.runtime import workflow_graph
from datakeel.runtime.saver import SQLAlchemySaver
from datakeel.runtime.workflow_service import resume_workflow, start_workflow
from datakeel.storage.database import Database

if TYPE_CHECKING:
    from collections.abc import Sequence

    from langchain_core.runnables import RunnableConfig
    from sqlalchemy.engine.interfaces import DBAPIConnection
    from sqlalchemy.pool import ConnectionPoolEntry

    from datakeel.ontology.tool_models import ToolOutcome


class ProcessRequest(BoundaryModel):
    """Bind the child only to a generated database schema, dataset, and local evidence files."""

    database_url: str
    schema_name: str | None = Field(default=None, pattern=r"^test_[0-9a-f]{32}$")
    dataset_id: str
    run_id: str = ""
    plan_id: str = ""
    phase: Literal["pause", "resume_commit", "resume"]
    marker: Path
    result: Path


def database(request: ProcessRequest) -> Database:
    """Connect only to the parent's disposable local test database and selected schema."""
    db = Database(request.database_url)
    if not db.sqlite:
        assert db.engine.url.host in {"localhost", "127.0.0.1"}
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
        original_execute = workflow_graph.execute_approved

        def execute(db: Database, plan_id: str) -> ToolOutcome:
            outcome = original_execute(db, plan_id)
            assert outcome.run is not None
            assert outcome.run.status == "SUCCEEDED"
            _kill(request)
            return outcome

        patch.setattr(workflow_graph, "execute_approved", execute)


def main() -> None:
    """Leave actual persisted facts behind when the process is terminated without cleanup."""
    request = ProcessRequest.model_validate_json(Path(sys.argv[1]).read_text(encoding="utf-8"))
    db = database(request)
    with pytest.MonkeyPatch.context() as patch:
        _install_fault(request, patch)
        if request.phase == "pause":
            events = list(
                start_workflow(
                    db,
                    "low-quality-cleanup",
                    WorkflowStart(
                        inputs=JsonDocument({"dataset_id": request.dataset_id, "quality_max": 0}),
                        idempotency_key="crash-start",
                    ),
                )
            )
        else:
            events = list(
                resume_workflow(
                    db,
                    request.run_id,
                    ResumeInput(plan_id=request.plan_id, idempotency_key="crash-resume"),
                )
            )
        request.result.write_text(
            "\n".join(item.model_dump_json() for item in events), encoding="utf-8"
        )
    db.engine.dispose()


if __name__ == "__main__":
    main()
