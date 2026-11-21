# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Wire isolated child graphs to ordered parent dispatch and live progress."""

from collections.abc import Callable, Generator, Iterator, Sequence
from concurrent.futures import Future
from contextlib import contextmanager
from contextvars import copy_context
from threading import Lock
from typing import Protocol

from datakeel.agent.models import AgentEvent
from datakeel.core.agent_models import Conversation, MessageInput, Provider, ToolCall
from datakeel.core.models import JsonDocument
from datakeel.delegation import parallel
from datakeel.delegation.models import ChildResult, DelegationResult
from datakeel.delegation.service import delegate
from datakeel.ontology.tool_models import ToolOutcome
from datakeel.storage import conversation_store as memory
from datakeel.storage.database import Database
from datakeel.storage.harness_service import list_traces


class ChildGraph(Protocol):
    """Require synchronous execution and the child's actually used memory identities."""

    run: Callable[[], Iterator[AgentEvent]]
    used_memories: Callable[[], list[str]]


class DelegationExecutor:
    """Keep one reply's serial count and nested events outside checkpoint configuration."""

    def __init__(
        self,
        db: Database,
        parent: Conversation,
        provider: Provider | None,
        factory: Callable[[Database, str, str, Provider | None], ChildGraph],
        emit: Callable[[AgentEvent], None] = lambda _: None,
    ) -> None:
        """Share the provider object while every child receives an independent lease."""
        self.db, self.parent, self.provider, self.factory = db, parent, provider, factory
        self.emit, self._emit_context, self._emit_lock = emit, copy_context(), Lock()
        self._futures = dict[str, Future[DelegationResult]]()
        self.ordinal = 0
        self.events: list[AgentEvent] = []
        self.stop_reason: str | None = None

    @contextmanager
    def parallel_delegations(
        self, calls: Sequence[ToolCall], state: parallel.ParallelDelegationInput
    ) -> Generator[list[ToolCall]]:
        """Submit an eligible prefix and join every child before leaving this turn."""
        batch = parallel.plan_parallel_delegations(calls, state)
        with parallel.parallel_delegation_futures(
            batch, lambda call, ordinal: delegate(self.db, self.parent, call, ordinal, self._run)
        ) as self._futures:
            try:
                yield [call for call, _ in batch]
            finally:
                self._futures.clear()

    def invoke(self, call: ToolCall) -> ToolOutcome:
        """Execute one child synchronously or return its previously recorded conclusion."""
        self.ordinal += 1
        future = self._futures.pop(call.id, None)
        db, parent, ordinal = self.db, self.parent, self.ordinal
        result = future.result() if future else delegate(db, parent, call, ordinal, self._run)
        self.events.extend(AgentEvent.model_validate(item.root) for item in result.events)
        if self.stop_reason != "canary_leak":
            self.stop_reason = result.stop_reason or self.stop_reason
        return result.outcome

    def wait(self, call: ToolCall) -> None:
        """Finish a submitted invocation before the catalog checks its durable replay."""
        if future := self._futures.get(call.id):
            future.result()

    def drain(self) -> list[AgentEvent]:
        """Emit nested events once before their parent's completed tool result."""
        events, self.events = self.events, []
        return events

    def _run(self, child: Conversation, task: str) -> ChildResult:
        lease = memory.begin(self.db, child.id, MessageInput(content=task))
        events, completed = list[AgentEvent](), False
        try:
            graph = self.factory(self.db, child.id, lease.token, self.provider)
            for event in graph.run():
                if event.event != "text_delta":
                    events.append(event)
                self._append(child.id, lease.token, event)
            done = AgentEvent(
                event="done",
                agent_name=child.agent_name,
                agent_path=child.agent_path,
                conversation_id=child.id,
                tokens=sum(trace.accounted_tokens for trace in list_traces(self.db, child.id)),
                used_memory_ids=graph.used_memories(),
            )
            events.append(done)
            self._append(child.id, lease.token, done)
            completed = True
        finally:
            memory.finish(self.db, child.id, lease.token, completed=completed)
        own = [event for event in reversed(events) if event.agent_path == child.agent_path]
        return ChildResult(
            summary=next((e.text for e in own if e.event == "text" and e.text), ""),
            events=[JsonDocument.model_validate(event.model_dump(mode="json")) for event in events],
            stop_reason=next((e.stop_reason for e in own if e.stop_reason), None),
        )

    def _append(self, child_id: str, token: str, event: AgentEvent) -> None:
        if event.event != "text_delta":
            payload = JsonDocument.model_validate(event.model_dump(mode="json"))
            memory.append(self.db, child_id, token, event=payload)
        with self._emit_lock:
            self._emit_context.run(self.emit, event)
