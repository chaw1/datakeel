# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Bounded controlled-tool loop with durable metering for every provider attempt."""

from collections.abc import Generator, Iterator
from time import perf_counter
from typing import Literal

import httpx
from pydantic import ValidationError as ModelValidationError

from datakeel.agent.confirm import execute_reversible
from datakeel.agent.context import allocate_tokens, assemble
from datakeel.agent.demo import DemoProvider
from datakeel.agent.guards import LoopGuard
from datakeel.agent.memory import workspace
from datakeel.agent.models import AgentEvent
from datakeel.agent.tools import ToolCatalog
from datakeel.core.agent_models import ChatMessage, ModelRequest, ModelResponse, Provider, ToolCall
from datakeel.core.errors import BudgetError, DatakeelError
from datakeel.core.harness_models import BudgetRequest, TraceInput
from datakeel.core.models import JsonDocument
from datakeel.harness.service import reserve, settle
from datakeel.ontology.tool_models import ToolCallContext, ToolOutcome
from datakeel.storage import conversation_store as memory
from datakeel.storage.database import Database


class AgentLoop:
    """Own one response while all transcript and budget state remains in storage."""

    def __init__(self, db: Database, conversation_id: str, token: str, provider: Provider) -> None:
        """Attach one provider and independent progress guards to the response lease."""
        self.db, self.conversation_id, self.token, self.provider = (
            db,
            conversation_id,
            token,
            provider,
        )
        self.catalog = ToolCatalog(memory.get(db, conversation_id))
        self.guard = LoopGuard()
        self.context = ToolCallContext(agent_id="datakeel-agent", session_id=conversation_id)

    def run(self) -> Iterator[AgentEvent]:
        """Stop on a complete answer, a human plan, a budget, or a progress guard."""
        config = memory.get(self.db, self.conversation_id).config
        for _ in range(config.max_turns):
            try:
                response = self._complete()
            except BudgetError:
                yield _stopped("budget_exceeded")
                return
            except (DatakeelError, httpx.HTTPError, ModelValidationError, ValueError) as error:
                yield _stopped("provider_error", type(error).__name__)
                return
            self._append(
                ChatMessage(
                    role="assistant", content=response.content, tool_calls=response.tool_calls
                )
            )
            if response.content:
                yield AgentEvent(event="text", text=response.content)
            if not response.tool_calls:
                if response.content:
                    return
                reason = self.guard.observe_empty()
                if reason:
                    yield _stopped(reason)
                    return
                continue
            reason = yield from self._process_calls(response.tool_calls, dry_run=config.dry_run)
            if reason:
                yield _stopped(reason)
                return
        yield _stopped("max_turns")

    def _process_calls(
        self, calls: list[ToolCall], *, dry_run: bool
    ) -> Generator[AgentEvent, None, str | None]:
        for index, call in enumerate(calls):
            yield AgentEvent(event="tool_call", call=call)
            events, reason = self._dispatch(call, dry_run=dry_run)
            yield from events
            if reason:
                for pending in calls[index + 1 :]:
                    self._tool_message(
                        pending, ToolOutcome(name=pending.name, status="FAILED", error=reason)
                    )
                return reason
        return None

    def _complete(self) -> ModelResponse:
        conversation = memory.get(self.db, self.conversation_id)
        request = assemble(
            conversation,
            self.catalog.core,
            list(self.catalog.loaded.values()),
            workspace(self.db, conversation),
        )
        reservation = reserve(
            self.db,
            BudgetRequest(
                conversation_id=conversation.id,
                model=request.model,
                input_tokens=_input_bound(self.provider, request),
                max_output_tokens=request.max_output_tokens,
                limits=conversation.config.budget,
            ),
        )
        started = perf_counter()
        try:
            response = self.provider.complete(request)
        except Exception:
            self._settle(
                request,
                reservation.id,
                ModelResponse(stop_reason="provider_error"),
                started,
                billing_status="unknown",
            )
            raise
        self._settle(request, reservation.id, response, started)
        return response

    def _settle(
        self,
        request: ModelRequest,
        reservation_id: str,
        response: ModelResponse,
        started: float,
        *,
        billing_status: Literal["actual", "unknown"] = "actual",
    ) -> None:
        conversation = memory.append(self.db, self.conversation_id, self.token, model_call=True)
        trace = settle(
            self.db,
            reservation_id,
            TraceInput(
                conversation_id=conversation.id,
                turn=conversation.turns,
                model=request.model,
                provider=conversation.config.provider,
                segments=allocate_tokens(request.segments, response.usage.input_tokens),
                usage=response.usage,
                latency_ms=(perf_counter() - started) * 1000,
                stop_reason=response.stop_reason,
                tool_calls=len(response.tool_calls),
                billing_status=billing_status,
            ),
        )
        if trace.budget_exceeded:
            msg = "Observed provider consumption exceeded the available budget"
            raise BudgetError(msg)

    def _dispatch(self, call: ToolCall, *, dry_run: bool) -> tuple[list[AgentEvent], str | None]:
        reason = self.guard.observe_call(call)
        if reason:
            outcome = ToolOutcome(name=call.name, status="FAILED", error=reason)
            self._tool_message(call, outcome)
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
        self._tool_message(call, outcome)
        return events, reason

    def _tool_message(self, call: ToolCall, outcome: ToolOutcome) -> None:
        if outcome.plan is not None or outcome.run is not None:
            outcome = outcome.model_copy(update={"content": JsonDocument({})})
        self._append(
            ChatMessage(
                role="tool", content=outcome.model_dump_json(), tool_call_id=call.id, name=call.name
            )
        )

    def _append(self, message: ChatMessage) -> None:
        memory.append(self.db, self.conversation_id, self.token, message=message)


def _stopped(reason: str, detail: str = "") -> AgentEvent:
    return AgentEvent(
        event="stopped", stop_reason=reason, text=f"Stopped: {reason}. {detail}".strip()
    )


def _input_bound(provider: Provider, request: ModelRequest) -> int:
    """Use exact offline demo accounting and conservative bounds for external providers."""
    tokens = sum(segment.tokens for segment in request.segments)
    return max(1, tokens // 4) if isinstance(provider, DemoProvider) else tokens
