# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Dispatch controlled tools while preserving transcript and event contracts."""

from datakeel.agent.confirm import execute_reversible
from datakeel.agent.guards import LoopGuard
from datakeel.agent.models import AgentEvent
from datakeel.agent.tools import ToolCatalog
from datakeel.core.agent_models import ChatMessage, ToolCall
from datakeel.core.models import JsonDocument
from datakeel.ontology.tool_models import ToolCallContext, ToolOutcome
from datakeel.storage import conversation_store as memory
from datakeel.storage.database import Database


class ToolDispatcher:
    """Keep tool effects independent of the framework scheduler."""

    def __init__(self, db: Database, conversation_id: str, token: str, guard: LoopGuard) -> None:
        """Attach the response lease and already restored progress counters."""
        self.db, self.conversation_id, self.token, self.guard = db, conversation_id, token, guard
        self.catalog = ToolCatalog(memory.get(db, conversation_id))
        self.context = ToolCallContext(agent_id="datakeel-agent", session_id=conversation_id)

    def dispatch(self, call: ToolCall, *, dry_run: bool) -> tuple[list[AgentEvent], str | None]:
        """Apply the existing guard, tool policy and automatic reversible action behavior."""
        reason = self.guard.observe_call(call)
        if reason:
            outcome = ToolOutcome(name=call.name, status="FAILED", error=reason)
            self.tool_message(call, outcome)
            return [AgentEvent(event="tool_result", outcome=outcome)], reason
        outcome = self.catalog.invoke(self.db, call, self.context)
        events = [AgentEvent(event="tool_result", outcome=outcome)]
        reason = self.guard.observe_outcome(outcome)
        if outcome.plan is not None:
            events.append(AgentEvent(event="plan", outcome=outcome))
            execution = execute_reversible(self.db, outcome, self.context, dry_run=dry_run)
            if execution is not None:
                events.append(AgentEvent(event="receipt", outcome=execution))
                outcome = outcome.model_copy(
                    update={"run": execution.run, "error": execution.error}
                )
                if execution.status == "FAILED":
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
        self._append(
            ChatMessage(
                role="tool", content=outcome.model_dump_json(), tool_call_id=call.id, name=call.name
            )
        )

    def _append(self, message: ChatMessage) -> None:
        memory.append(self.db, self.conversation_id, self.token, message=message)
