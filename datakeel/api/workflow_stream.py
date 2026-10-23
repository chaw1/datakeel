# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Propagate HTTP disconnects into synchronous workflow execution before closing its stream."""

from collections.abc import Awaitable, Callable, Generator, Iterator
from functools import partial
from itertools import chain
from threading import Event

from anyio import create_task_group
from starlette.background import BackgroundTask
from starlette.types import Receive, Scope, Send

from datakeel.api.routes.agent import EventStreamResponse
from datakeel.core.workflow_models import WorkflowEvent


def _encode(events: Iterator[WorkflowEvent], first: WorkflowEvent | None) -> Iterator[str]:
    try:
        for event in chain([first] if first is not None else [], events):
            yield f"id: {event.id}\nevent: {event.event}\ndata: {event.model_dump_json()}\n\n"
    except InterruptedError:
        # The execution generator commits interruption facts before propagating cancellation.
        return


class WorkflowStreamResponse(EventStreamResponse):
    """Monitor disconnects even while a worker thread is blocked inside task polling."""

    def __init__(self, events: Generator[WorkflowEvent, None, None], cancelled: Event) -> None:
        """Validate the first event before sending headers and retain cooperative cancellation."""
        self.cancelled = cancelled
        first = next(events, None)
        super().__init__(
            _encode(events, first),
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            background=BackgroundTask(events.close),
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Watch receive for all ASGI versions and wait for the writer before generator close."""
        del scope
        try:
            async with create_task_group() as tasks:

                async def finish(operation: Callable[[], Awaitable[None]]) -> None:
                    try:
                        await operation()
                    except OSError:
                        # Sending can report a disconnected client before receive does.
                        self.cancelled.set()
                    finally:
                        self.cancelled.set()
                        tasks.cancel_scope.cancel()

                tasks.start_soon(finish, partial(self.stream_response, send))
                await finish(partial(self.listen_for_disconnect, receive))
        finally:
            self.cancelled.set()
            if self.background is not None:
                await self.background()
