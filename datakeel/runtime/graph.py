# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Synchronous checkpointed graph scheduling for the existing controlled Agent behavior."""

from collections.abc import Iterator
from functools import partial
from typing import TYPE_CHECKING, Literal, cast

import httpx
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt
from pydantic import Field, JsonValue
from pydantic import ValidationError as ModelValidationError

from datakeel.agent.dispatch import ToolDispatcher
from datakeel.agent.guards import LoopGuard
from datakeel.agent.metering import ModelMeter
from datakeel.agent.models import AgentEvent
from datakeel.core.agent_models import ChatMessage, Provider, ToolCall
from datakeel.core.errors import BudgetError, DatakeelError
from datakeel.core.models import BoundaryModel
from datakeel.ontology.tool_models import ToolOutcome
from datakeel.runtime import DURABILITY
from datakeel.runtime.chat import complete
from datakeel.runtime.saver import SQLAlchemySaver
from datakeel.runtime.tracing import tracing_disabled
from datakeel.storage import conversation_store as memory
from datakeel.storage.database import Database

if TYPE_CHECKING:
    from langchain_core.runnables import RunnableConfig


class GraphState(BoundaryModel):
    """Checkpoint only IDs, JSON strings and primitive counters, never credentials or objects."""

    turn: int = 0
    calls: list[str] = Field(default_factory=list[str])
    events: list[str] = Field(default_factory=list[str])
    guard: str = ""
    plan_id: str = ""
    pending_call: str = ""
    next_node: Literal["model", "tools", "approval_gate", "__end__"] = "model"


def _stopped(reason: str, detail: str = "") -> AgentEvent:
    return AgentEvent(
        event="stopped", stop_reason=reason, text=f"Stopped: {reason}. {detail}".strip()
    )


def approval_gate(state: GraphState) -> dict[str, str]:
    """Pause only; replaying this node never performs business work or grants authority."""
    interrupt(state.plan_id)
    return {}


def _route(state: GraphState) -> str:
    return state.next_node


class AgentGraph:
    """Bind ephemeral response dependencies to a graph with durable primitive execution state."""

    def __init__(self, db: Database, conversation_id: str, token: str, provider: Provider) -> None:
        """Keep the response token on this ephemeral instance, outside config and metadata."""
        self.db, self.conversation_id, self.token, self.provider = (
            db,
            conversation_id,
            token,
            provider,
        )
        self.guard = LoopGuard()
        self.maximum = memory.get(db, conversation_id).config.max_turns
        self.saver = SQLAlchemySaver(db)
        self.config: RunnableConfig = {
            "configurable": {"thread_id": conversation_id},
            "recursion_limit": self.maximum * 3 + 20,
        }
        builder = StateGraph(GraphState)
        builder.add_node("model", self._model_node)
        builder.add_node("tools", self._tools_node)
        builder.add_node("approval_gate", approval_gate)
        builder.add_edge(START, "model")
        for node in ("model", "tools"):
            builder.add_conditional_edges(node, _route)
        builder.add_edge("approval_gate", END)
        self.graph = builder.compile(checkpointer=self.saver)

    def run(self) -> Iterator[AgentEvent]:
        """Start a fresh user response while retaining all authoritative business history."""
        self.saver.delete_thread(self.conversation_id)
        with tracing_disabled():
            for update in self.graph.stream(
                cast("GraphState", GraphState().model_dump()),
                self.config,
                stream_mode="updates",
                durability=DURABILITY,
            ):
                for value in cast("dict[str, object]", update).values():
                    if isinstance(value, dict):
                        events = cast("dict[str, list[str]]", value).get("events", [])
                        yield from (AgentEvent.model_validate_json(event) for event in events)
            if self.graph.get_state(self.config).interrupts:
                yield _stopped("approval_required")

    def _model(self, state: GraphState) -> GraphState:
        state = state.model_copy(update={"events": []})
        self.guard.restore(state.guard)
        meter = ModelMeter(self.db, self.conversation_id, self.token, self.provider)
        try:
            response = meter.complete(partial(complete, self.provider))
        except BudgetError:
            return self._stop(state, "budget_exceeded")
        except (DatakeelError, httpx.HTTPError, ModelValidationError, ValueError) as error:
            return self._stop(state, "provider_error", type(error).__name__)
        memory.append(
            self.db,
            self.conversation_id,
            self.token,
            message=ChatMessage(
                role="assistant", content=response.content, tool_calls=response.tool_calls
            ),
        )
        events = [AgentEvent(event="text", text=response.content)] if response.content else []
        state = state.model_copy(
            update={
                "turn": state.turn + 1,
                "calls": [call.model_dump_json() for call in response.tool_calls],
                "events": [event.model_dump_json() for event in events],
                "next_node": "tools" if response.tool_calls else END,
            }
        )
        if not response.content and not response.tool_calls:
            reason = self.guard.observe_empty()
            return self._stop(state, reason) if reason else self._continue(state)
        return state

    def _tools(self, state: GraphState) -> GraphState:
        self.guard.restore(state.guard)
        dispatcher = ToolDispatcher(self.db, self.conversation_id, self.token, self.guard)
        dry_run = memory.get(self.db, self.conversation_id).config.dry_run
        calls = [ToolCall.model_validate_json(item) for item in state.calls]
        events: list[AgentEvent] = []
        reason: str | None = None
        results: list[AgentEvent] = []
        pending_call = ""
        for index, call in enumerate(calls):
            events.append(AgentEvent(event="tool_call", call=call))
            results, reason = dispatcher.dispatch(call, dry_run=dry_run)
            events.extend(results)
            if reason:
                pending_call = call.model_dump_json()
                for pending in calls[index + 1 :]:
                    dispatcher.tool_message(
                        pending, ToolOutcome(name=pending.name, status="FAILED", error=reason)
                    )
                break
        state = state.model_copy(update={"events": [event.model_dump_json() for event in events]})
        if reason == "approval_required":
            plan = next(
                event.outcome.plan for event in results if event.event == "plan" and event.outcome
            )
            return state.model_copy(
                update={
                    "plan_id": plan.id if plan else "",
                    "pending_call": pending_call,
                    "guard": self.guard.snapshot(),
                    "next_node": "approval_gate",
                }
            )
        return self._stop(state, reason) if reason else self._continue(state)

    def _continue(self, state: GraphState) -> GraphState:
        if state.turn >= self.maximum:
            return self._stop(state, "max_turns")
        return state.model_copy(update={"next_node": "model", "guard": self.guard.snapshot()})

    def _model_node(self, state: GraphState) -> dict[str, JsonValue]:
        return self._model(state).model_dump(mode="json")

    def _tools_node(self, state: GraphState) -> dict[str, JsonValue]:
        return self._tools(state).model_dump(mode="json")

    def _stop(self, state: GraphState, reason: str, detail: str = "") -> GraphState:
        return state.model_copy(
            update={
                "events": [*state.events, _stopped(reason, detail).model_dump_json()],
                "guard": self.guard.snapshot(),
                "next_node": END,
            }
        )
