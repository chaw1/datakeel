# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Synchronous checkpointed graph scheduling for the existing controlled Agent behavior."""

from collections.abc import Iterator
from functools import partial
from typing import TYPE_CHECKING, Literal, cast

import httpx
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt
from pydantic import Field, JsonValue
from pydantic import ValidationError as ModelValidationError

from datakeel.agent.dispatch import ToolDispatcher
from datakeel.agent.guards import LoopGuard
from datakeel.agent.metering import ModelMeter
from datakeel.agent.models import AgentEvent
from datakeel.agent.recovery import execute_approved
from datakeel.core.agent_models import ChatMessage, Provider, ResumeInput, ToolCall
from datakeel.core.canary import response_leaks
from datakeel.core.errors import BudgetError, ConflictError, DatakeelError, ValidationError
from datakeel.core.models import BoundaryModel
from datakeel.delegation.policy import ancestor_leak
from datakeel.ontology.functions import PARAMETER_MODELS
from datakeel.ontology.tool_models import ToolOutcome
from datakeel.runtime import DURABILITY
from datakeel.runtime.chat import complete
from datakeel.runtime.delegation_graph import DelegationExecutor
from datakeel.runtime.saver import SQLAlchemySaver
from datakeel.runtime.tracing import tracing_disabled
from datakeel.storage import conversation_store as memory
from datakeel.storage.conversation_authorization import authorize_resume, record_audit
from datakeel.storage.conversation_secrets import get_canary
from datakeel.storage.database import Database

if TYPE_CHECKING:
    from langchain_core.runnables import RunnableConfig


class GraphState(BoundaryModel):
    """Checkpoint only IDs, JSON strings and primitive counters, never credentials or objects."""

    turn: int = 0
    calls: list[str] = Field(default_factory=list[str])
    events: list[str] = Field(default_factory=list[str])
    used_memory_ids: list[str] = Field(default_factory=list[str])
    guard: str = ""
    plan_id: str = ""
    pending_call: str = ""
    response_has_plan: bool = False
    response_has_tool_result: bool = False
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

    def __init__(
        self, db: Database, conversation_id: str, token: str, provider: Provider | None
    ) -> None:
        """Keep the response token on this ephemeral instance, outside config and metadata."""
        self.db, self.conversation_id, self.token, self.provider = (
            db,
            conversation_id,
            token,
            provider,
        )
        self.guard = LoopGuard()
        self.workflow_confirmation_required = False
        self.conversation = memory.get(db, conversation_id)
        self.maximum = self.conversation.config.max_turns
        self.saver = SQLAlchemySaver(db)
        self.config: RunnableConfig = {
            "configurable": {"thread_id": conversation_id},
            "recursion_limit": self.maximum * 3 + 20,
        }
        builder = StateGraph(GraphState)
        builder.add_node("model", self._model_node)
        builder.add_node("tools", self._tools_node)
        builder.add_node("approval_gate", approval_gate)
        builder.add_node("execute", self._execute)
        builder.add_edge(START, "model")
        for node in ("model", "tools"):
            builder.add_conditional_edges(node, _route)
        builder.add_edge("approval_gate", "execute")
        builder.add_conditional_edges("execute", _route)
        self.graph = builder.compile(checkpointer=self.saver)

    def invalidate(self) -> None:
        """Discard an accepted new message's old pause before provider setup can fail."""
        pending = self.pending_plan()
        if pending:
            record_audit(
                self.db, self.conversation_id, pending, "INTERRUPT_INVALIDATED", "new_message"
            )
        self.saver.delete_thread(self.conversation_id)

    def run(self) -> Iterator[AgentEvent]:
        """Start a fresh user response while retaining all authoritative business history."""
        self.invalidate()
        return self._stream(cast("GraphState", GraphState().model_dump()))

    def pending_plan(self) -> str:
        """Read a suspended gate or an interrupted execution following an authorized gate."""
        snapshot = self.graph.get_state(self.config)
        if not set(snapshot.next).intersection({"approval_gate", "execute"}):
            return ""
        return GraphState.model_validate(snapshot.values).plan_id

    def used_memories(self) -> list[str]:
        """Project only identities of memories actually sent in this response's model calls."""
        snapshot = self.graph.get_state(self.config)
        return GraphState.model_validate(snapshot.values).used_memory_ids

    def resume(self, request: ResumeInput) -> Iterator[AgentEvent]:
        """Check real approval immediately, before lazy execution or provider construction."""
        authorize_resume(self.db, self.conversation_id, request.plan_id, self.pending_plan())
        snapshot = self.graph.get_state(self.config)
        values = {
            item.id: request.plan_id
            for item in snapshot.interrupts
            if item.value == request.plan_id
        }
        command: Command[str] | None = Command(resume=values) if values else None
        return self._stream(command)

    def _stream(self, value: GraphState | Command[str] | None) -> Iterator[AgentEvent]:
        with tracing_disabled():
            for update in self.graph.stream(
                value,
                self.config,
                stream_mode="updates",
                durability=DURABILITY,
            ):
                for node_update in cast("dict[str, object]", update).values():
                    if isinstance(node_update, dict):
                        events = cast("dict[str, list[str]]", node_update).get("events", [])
                        for event in events:
                            item = AgentEvent.model_validate_json(event)
                            yield (
                                item
                                if item.agent_path != "main"
                                else item.model_copy(
                                    update={
                                        "agent_path": self.conversation.agent_path,
                                        "agent_name": self.conversation.agent_name,
                                        "conversation_id": self.conversation_id,
                                    }
                                )
                            )
            if self.graph.get_state(self.config).interrupts:
                yield _stopped("approval_required")

    def _execute(self, state: GraphState) -> dict[str, JsonValue]:
        dispatcher = ToolDispatcher(self.db, self.conversation_id, self.token, self.guard)
        call = ToolCall.model_validate_json(state.pending_call)
        recorded = dispatcher.catalog.invoke(self.db, call, dispatcher.context)
        if recorded.plan is None or recorded.plan.id != state.plan_id:
            msg = "Paused tool outcome no longer matches the approved plan"
            raise ConflictError(msg)
        outcome = execute_approved(self.db, state.plan_id)
        state = state.model_copy(
            update={"events": [AgentEvent(event="receipt", outcome=outcome).model_dump_json()]}
        )
        self.guard.restore(state.guard)
        result = (
            self._stop(state, "execution_failed")
            if outcome.status == "FAILED"
            else self._continue(state)
        )
        return result.model_dump(mode="json")

    def _model(self, state: GraphState) -> GraphState:
        if self.provider is None:
            msg = "A configured provider is required to execute a model node"
            raise ValidationError(msg)
        state = state.model_copy(update={"events": []})
        self.guard.restore(state.guard)
        meter = ModelMeter(self.db, self.conversation_id, self.token, self.provider)
        try:
            response = meter.complete(
                partial(complete, self.provider),
                has_plan=state.response_has_plan,
                has_tool_result=state.response_has_tool_result,
            )
        except BudgetError:
            return self._stop(self._remember(state, meter), "budget_exceeded")
        except (DatakeelError, httpx.HTTPError, ModelValidationError, ValueError) as error:
            return self._stop(self._remember(state, meter), "provider_error", type(error).__name__)
        state = self._remember(state, meter)
        if response_leaks(get_canary(self.db, self.conversation_id), response) or ancestor_leak(
            self.db, self.conversation, response
        ):
            record_audit(self.db, self.conversation_id, "", "CANARY_LEAK", "model_output")
            return self._stop(state, "canary_leak")
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

    @staticmethod
    def _remember(state: GraphState, meter: ModelMeter) -> GraphState:
        return state.model_copy(
            update={
                "used_memory_ids": list(
                    dict.fromkeys([*state.used_memory_ids, *meter.used_memory_ids])
                )
            }
        )

    def _tools(self, state: GraphState) -> GraphState:
        self.guard.restore(state.guard)
        dispatcher = ToolDispatcher(self.db, self.conversation_id, self.token, self.guard)
        delegated = DelegationExecutor(self.db, self.conversation, self.provider, AgentGraph)
        dry_run = memory.get(self.db, self.conversation_id).config.dry_run
        calls = [ToolCall.model_validate_json(item) for item in state.calls]
        events: list[AgentEvent] = []
        reason: str | None = None
        results: list[AgentEvent] = []
        pending_call = ""
        for index, call in enumerate(calls):
            events.append(AgentEvent(event="tool_call", call=call))
            results, reason = self._dispatch_tool(dispatcher, call, delegated, dry_run=dry_run)
            events.extend(delegated.drain())
            reason = delegated.stop_reason or reason
            events.extend(results)
            if reason:
                pending_call = call.model_dump_json()
                for pending in calls[index + 1 :]:
                    dispatcher.tool_message(
                        pending, ToolOutcome(name=pending.name, status="FAILED", error=reason)
                    )
                break
        state = state.model_copy(
            update={
                "events": [event.model_dump_json() for event in events],
                "response_has_plan": state.response_has_plan
                or any(event.event == "plan" for event in events),
                "response_has_tool_result": state.response_has_tool_result
                or any(event.event == "tool_result" for event in events),
            }
        )
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

    def _dispatch_tool(
        self,
        dispatcher: ToolDispatcher,
        call: ToolCall,
        delegated: DelegationExecutor,
        *,
        dry_run: bool,
    ) -> tuple[list[AgentEvent], str | None]:
        if self.workflow_confirmation_required and call.name not in {
            *PARAMETER_MODELS,
            "tool_search",
        }:
            reason = "workflow_confirmation_required"
            outcome = ToolOutcome(name=call.name, status="FAILED", error=reason)
            dispatcher.tool_message(call, outcome)
            return [AgentEvent(event="tool_result", outcome=outcome)], reason
        return dispatcher.dispatch(call, dry_run=dry_run, local=delegated.invoke)

    def _continue(self, state: GraphState) -> GraphState:
        if state.turn >= self.maximum:
            return self._stop(state, "max_turns")
        return state.model_copy(update={"next_node": "model", "guard": self.guard.snapshot()})

    def _model_node(self, state: GraphState) -> dict[str, JsonValue]:
        return self._model(state).model_dump(mode="json")

    def _tools_node(self, state: GraphState) -> dict[str, JsonValue]:
        result = self._tools(state)
        identifiers = [
            identifier
            for item in result.events
            for identifier in AgentEvent.model_validate_json(item).used_memory_ids
        ]
        return result.model_copy(
            update={"used_memory_ids": list(dict.fromkeys([*result.used_memory_ids, *identifiers]))}
        ).model_dump(mode="json")

    def _stop(self, state: GraphState, reason: str, detail: str = "") -> GraphState:
        return state.model_copy(
            update={
                "events": [*state.events, _stopped(reason, detail).model_dump_json()],
                "guard": self.guard.snapshot(),
                "next_node": END,
            }
        )
