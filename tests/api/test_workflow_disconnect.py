# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Deliver ASGI disconnects while real workflow execution is blocked or durably paused."""

from __future__ import annotations

import asyncio
from threading import Event, Timer
from time import monotonic, sleep
from typing import TYPE_CHECKING, cast

import pytest

from datakeel.actions.service import list_runs
from datakeel.api.workflow_stream import WorkflowStreamResponse
from datakeel.core.models import JsonDocument
from datakeel.core.workflow_models import WorkflowEvent, WorkflowStart
from datakeel.runtime.workflow_graph import WorkflowGraph
from datakeel.runtime.workflow_service import start_workflow
from datakeel.storage.tool_invocations import list_invocations
from datakeel.storage.workflow_recovery import list_audit
from datakeel.storage.workflow_store import get_run
from datakeel.workflows.execution import WorkflowHooks
from tests.workflows.conftest import create_dataset

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from starlette.types import Message, Scope

    from datakeel.storage.database import Database


async def _disconnect(
    response: WorkflowStreamResponse,
    spec_version: str,
    target: Callable[[WorkflowEvent], bool],
    polling: Event | None,
) -> tuple[list[WorkflowEvent], float]:
    """Notify the actual response after a target SSE event, including a blocked next call."""
    ready = asyncio.Event()
    observed: list[WorkflowEvent] = []
    disconnected_at = 0.0

    async def receive() -> Message:
        nonlocal disconnected_at
        await ready.wait()
        if polling is not None:
            await asyncio.sleep(0.1)
            assert polling.is_set(), "The real wait node never entered its polling sleep"
        disconnected_at = monotonic()
        return {"type": "http.disconnect"}

    async def send(message: Message) -> None:
        for line in cast("bytes", message.get("body", b"")).decode().splitlines():
            if not line.startswith("data: "):
                continue
            event = WorkflowEvent.model_validate_json(line.removeprefix("data: "))
            observed.append(event)
            if target(event):
                ready.set()
                if polling is None:
                    # Hold the paused event's send until the disconnect listener cancels it.
                    await asyncio.Future[None]()

    scope: Scope = {"type": "http", "asgi": {"version": "3.0", "spec_version": spec_version}}
    await asyncio.wait_for(response(scope, receive, send), timeout=4)
    assert disconnected_at > 0, "The response completed before the injected disconnect"
    return observed, monotonic() - disconnected_at


def _call_disconnected(
    response: WorkflowStreamResponse,
    spec_version: str,
    target: Callable[[WorkflowEvent], bool],
    polling: Event | None = None,
) -> tuple[list[WorkflowEvent], float]:
    """Bound a broken listener without allowing the fixture to wait for its 60-second timeout."""
    rescue = Timer(3, response.cancelled.set)
    rescue.start()
    try:
        return asyncio.run(_disconnect(response, spec_version, target, polling))
    finally:
        rescue.cancel()
        rescue.join()


@pytest.mark.parametrize("spec_version", ["2.3", "2.4"])
def test_http_disconnect_interrupts_real_wait_without_worker(
    db: Database, tmp_path: Path, spec_version: str
) -> None:
    """A blocked synchronous wait must stop promptly and record the real disconnect."""
    dataset = create_dataset(db, tmp_path / "wait-disconnect")
    cancelled, polling = Event(), Event()

    def real_sleep(seconds: float) -> None:
        polling.set()
        sleep(seconds)

    events = start_workflow(
        db,
        "dataset-health",
        WorkflowStart(
            inputs=JsonDocument({"dataset_id": dataset.id}), idempotency_key="http-disconnect"
        ),
        hooks=WorkflowHooks(sleep=real_sleep, cancelled=cancelled.is_set),
    )
    observed, elapsed = _call_disconnected(
        WorkflowStreamResponse(events, cancelled),
        spec_version,
        lambda event: (
            event.step_id == "wait"
            and any(step.id == "wait" and step.status == "RUNNING" for step in event.run.steps)
        ),
        polling,
    )
    assert elapsed <= 2
    assert cancelled.is_set()
    run = get_run(db, observed[-1].run.id)
    assert run.status == "INTERRUPTED"
    assert run.error
    assert "disconnect" in run.error.lower()
    assert next(step.status for step in run.steps if step.id == "wait") == "FAILED"
    assert all(step.status == "PENDING" for step in run.steps[2:])
    assert {item.name for item in list_invocations(db, run.id)} == {"run_pipeline", "execute_plan"}
    assert [entry.kind for entry in list_audit(db, run.id)] == ["INTERRUPTED"]
    assert WorkflowGraph(db, run.id).pending_plan() == ""


@pytest.mark.parametrize("spec_version", ["2.3", "2.4"])
def test_http_disconnect_preserves_a_durable_approval_pause(
    db: Database, tmp_path: Path, spec_version: str
) -> None:
    """Closing a paused stream must retain its signed-resume checkpoint and pending plan."""
    dataset = create_dataset(db, tmp_path / "approval-disconnect")
    cancelled = Event()
    events = start_workflow(
        db,
        "low-quality-cleanup",
        WorkflowStart(
            inputs=JsonDocument({"dataset_id": dataset.id, "quality_max": 0}),
            idempotency_key="approval-disconnect",
        ),
        hooks=WorkflowHooks(cancelled=cancelled.is_set),
    )
    observed, elapsed = _call_disconnected(
        WorkflowStreamResponse(events, cancelled),
        spec_version,
        lambda event: event.run.status == "PAUSED",
    )
    assert elapsed <= 2
    run = get_run(db, observed[-1].run.id)
    assert run.status == "PAUSED"
    assert run.pending_plan_id is not None
    assert WorkflowGraph(db, run.id).pending_plan() == run.pending_plan_id
    assert next(step.status for step in run.steps if step.id == "delete") == "PAUSED"
    assert list_audit(db, run.id) == []
    assert not any(action.action_type == "delete_files" for action in list_runs(db))
