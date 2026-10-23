# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Wire isolated child graph instances to the parent's serial tool dispatch."""

from collections.abc import Callable, Iterator
from typing import Protocol

from datakeel.agent.models import AgentEvent
from datakeel.core.agent_models import Conversation, MessageInput, Provider, ToolCall
from datakeel.core.models import JsonDocument
from datakeel.delegation.models import ChildResult
from datakeel.delegation.service import delegate
from datakeel.ontology.tool_models import ToolOutcome
from datakeel.storage import conversation_store as memory
from datakeel.storage.database import Database
from datakeel.storage.harness_service import list_traces


class ChildGraph(Protocol):
    """Require only the ordinary synchronous graph entry point."""

    def run(self) -> Iterator[AgentEvent]:
        """Execute an independent child response with its own checkpoint thread."""
        ...

    def used_memories(self) -> list[str]:
        """Return identities actually supplied to this child or its descendants."""
        ...


GraphFactory = Callable[[Database, str, str, Provider | None], ChildGraph]


class DelegationExecutor:
    """Keep one reply's serial count and nested events outside checkpoint configuration."""

    def __init__(
        self, db: Database, parent: Conversation, provider: Provider | None, factory: GraphFactory
    ) -> None:
        """Share the provider object while every child receives an independent lease."""
        self.db, self.parent, self.provider, self.factory = db, parent, provider, factory
        self.ordinal = 0
        self.events: list[AgentEvent] = []
        self.stop_reason: str | None = None

    def invoke(self, call: ToolCall) -> ToolOutcome:
        """Execute one child synchronously or return its previously recorded conclusion."""
        self.ordinal += 1
        result = delegate(self.db, self.parent, call, self.ordinal, self._run)
        self.events.extend(AgentEvent.model_validate(item.root) for item in result.events)
        self.stop_reason = result.stop_reason
        return result.outcome

    def drain(self) -> list[AgentEvent]:
        """Emit nested events once before their parent's completed tool result."""
        events, self.events = self.events, []
        return events

    def _run(self, child: Conversation, task: str) -> ChildResult:
        lease = memory.begin(self.db, child.id, MessageInput(content=task))
        events: list[AgentEvent] = []
        completed = False
        try:
            graph = self.factory(self.db, child.id, lease.token, self.provider)
            for event in graph.run():
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
        return _result(child, events)

    def _append(self, child_id: str, token: str, event: AgentEvent) -> None:
        memory.append(
            self.db,
            child_id,
            token,
            event=JsonDocument.model_validate(event.model_dump(mode="json")),
        )


def _result(child: Conversation, events: list[AgentEvent]) -> ChildResult:
    return ChildResult(
        summary=next(
            (
                event.text
                for event in reversed(events)
                if event.event == "text" and event.text and event.agent_path == child.agent_path
            ),
            "",
        ),
        events=[JsonDocument.model_validate(event.model_dump(mode="json")) for event in events],
        stop_reason=next(
            (
                event.stop_reason
                for event in reversed(events)
                if event.stop_reason and event.agent_path == child.agent_path
            ),
            None,
        ),
    )
