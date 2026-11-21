# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Dispatch controlled tools while preserving transcript and event contracts."""

from collections.abc import Callable, Generator, Sequence
from concurrent.futures import Future
from contextlib import contextmanager

from datakeel.agent.confirm import execute_reversible
from datakeel.agent.guards import PING_WINDOW, REPEAT_LIMIT, LoopGuard
from datakeel.agent.models import AgentEvent
from datakeel.agent.tools import ToolCatalog
from datakeel.core.agent_models import ChatMessage, ToolCall
from datakeel.core.models import JsonDocument
from datakeel.ontology import tool_batch as reads
from datakeel.ontology.tool_models import ToolCallContext, ToolOutcome
from datakeel.storage import conversation_store as memory
from datakeel.storage.database import Database
from datakeel.storage.identity_sessions import session_actor


class ToolDispatcher:
    """Keep tool effects independent of the framework scheduler."""

    def __init__(self, db: Database, conversation_id: str, token: str, guard: LoopGuard) -> None:
        """Attach the response lease and already restored progress counters."""
        self.db, self.conversation_id, self.token, self.guard = db, conversation_id, token, guard
        self.catalog = ToolCatalog(memory.get(db, conversation_id))
        actor = session_actor(db, conversation_id)
        self.context = ToolCallContext(
            actor=actor, agent_id="datakeel-agent", session_id=conversation_id
        )
        self._futures = dict[str, Future[ToolOutcome]]()

    @contextmanager
    def parallel_reads(self, calls: Sequence[ToolCall]) -> Generator[list[ToolCall]]:
        """Run only a guard-safe read prefix and join workers before leaving the turn."""
        db, catalog, ctx = self.db, self.catalog, self.context
        batch = []
        if reads.can_parallelize(sqlite=db.sqlite, database=db.engine.url.database):
            visible = {tool.name for tool in catalog.core} | catalog.loaded.keys()
            state = reads.ParallelPlanInput.from_guard(
                self.guard, REPEAT_LIMIT, PING_WINDOW, catalog.conversation.allowed_tools, visible
            )
            batch = reads.plan_parallel_prefix(calls, state)
        with reads.parallel_read_futures(
            batch, lambda c: catalog.invoke(db, c, ctx)
        ) as self._futures:
            try:
                yield batch
            finally:
                self._futures.clear()

    def dispatch(
        self,
        call: ToolCall,
        *,
        dry_run: bool,
        local: Callable[[ToolCall], ToolOutcome] | None = None,
    ) -> tuple[list[AgentEvent], str | None]:
        """Apply the existing guard, tool policy and automatic reversible action behavior."""
        if reason := self.guard.observe_call(call):
            outcome = ToolOutcome(name=call.name, status="FAILED", error=reason)
            self.tool_message(call, outcome)
            return [AgentEvent(event="tool_result", outcome=outcome)], reason
        future = self._futures.pop(call.id, None)
        outcome = (
            future.result() if future else self.catalog.invoke(self.db, call, self.context, local)
        )
        events = [AgentEvent(event="tool_result", outcome=outcome)]
        reason = self.guard.observe_outcome(outcome)
        if outcome.plan is not None:
            events.append(AgentEvent(event="plan", outcome=outcome))
            executed = execute_reversible(self.db, outcome, self.context, dry_run=dry_run)
            if executed is not None:
                events.append(AgentEvent(event="receipt", outcome=executed))
                outcome = outcome.model_copy(update={"run": executed.run, "error": executed.error})
                if executed.status == "FAILED":
                    reason = "execution_failed"
            elif outcome.plan.requires_approval or dry_run:
                reason = "dry_run" if dry_run else "approval_required"
        self.tool_message(call, outcome)
        return events, reason

    def tool_message(self, call: ToolCall, outcome: ToolOutcome) -> None:
        """Close an assistant call once, including after a node is replayed."""
        messages = memory.get(self.db, self.conversation_id).messages
        last_call = max(
            (i for i, item in enumerate(messages) if any(c.id == call.id for c in item.tool_calls)),
            default=-1,
        )
        if any(item.tool_call_id == call.id for item in messages[last_call + 1 :]):
            return
        if outcome.plan is not None or outcome.run is not None:
            outcome = outcome.model_copy(update={"content": JsonDocument({})})
        message = ChatMessage(
            role="tool", content=outcome.model_dump_json(), tool_call_id=call.id, name=call.name
        )
        memory.append(self.db, self.conversation_id, self.token, message=message)
