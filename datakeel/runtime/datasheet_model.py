# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Reuse provider configuration and durable budget accounting for one paragraph draft."""

from time import perf_counter

from datakeel.agent.factory import provider_session
from datakeel.core.agent_models import (
    ChatMessage,
    ContextSegment,
    ModelRequest,
    ModelResponse,
    Provider,
)
from datakeel.core.context_tokens import allocate_tokens, estimate_tokens
from datakeel.core.datasheet_execution import DatasheetFence, DatasheetJob, DatasheetPrepared
from datakeel.core.errors import BudgetError, ConflictError, ValidationError
from datakeel.core.harness_models import BudgetRequest, TokenUsage, TraceInput
from datakeel.datasheets.destination import model_destination
from datakeel.datasheets.prompt import build_model_prompt
from datakeel.datasheets.templates import build_template
from datakeel.storage.budget_service import refund, reserve
from datakeel.storage.database import Database
from datakeel.storage.datasheet_jobs import validate_fence
from datakeel.storage.harness_service import list_traces, settle


class _OfflineProvider:
    def __init__(self, job: DatasheetJob, prepared: DatasheetPrepared) -> None:
        self.job, self.prepared = job, prepared

    def complete(self, request: ModelRequest) -> ModelResponse:
        """Emit deterministic recorded-shape paragraphs without constructing an SDK client."""
        if request.model != self.prepared.config.model:
            msg = "Offline datasheet request changed its frozen model"
            raise ValidationError(msg)
        checked = build_template(self.prepared.facts, self.job.language)
        return ModelResponse(content=checked.model_dump_json(include={"sections"}))


def _request(job: DatasheetJob, prepared: DatasheetPrepared) -> ModelRequest:
    prompt = build_model_prompt(prepared.facts, job.language)
    return ModelRequest(
        model=prepared.config.model,
        messages=[ChatMessage(role="user", content=prompt)],
        tools=[],
        segments=[
            ContextSegment(
                name="datasheet_facts", kind="volatile", text=prompt, tokens=estimate_tokens(prompt)
            )
        ],
        max_output_tokens=prepared.config.max_output_tokens,
        agent_path="datasheets",
    )


def _settle(
    db: Database,
    reservation_id: str,
    request: ModelRequest,
    job: DatasheetJob,
    response: ModelResponse,
    started: float,
) -> None:
    usage = response.usage if response.usage_known else TokenUsage()
    trace = settle(
        db,
        reservation_id,
        TraceInput(
            conversation_id=job.id,
            turn=max((trace.turn for trace in list_traces(db, job.id)), default=0) + 1,
            model=request.model,
            provider=job.provider,
            segments=allocate_tokens(request.segments, usage.input_tokens),
            usage=usage,
            latency_ms=(perf_counter() - started) * 1000,
            stop_reason=response.stop_reason,
            tool_calls=len(response.tool_calls),
            billing_status="actual" if response.usage_known else "unknown",
            call_type="extraction",
            agent_path="datasheets",
        ),
    )
    if trace.budget_exceeded:
        msg = "Observed datasheet usage exceeded its budget"
        raise BudgetError(msg)


def draft_with_model(
    db: Database,
    job: DatasheetJob,
    prepared: DatasheetPrepared,
    fence: DatasheetFence,
    supplied: Provider | None = None,
) -> str:
    """Reserve before invocation; settle every attempted completion and failure."""
    request = _request(job, prepared)
    validate_fence(db, job.id, fence)
    if model_destination(prepared.config) != prepared.target_url:
        msg = "Datasheet model endpoint changed after approval"
        raise ConflictError(msg)
    if prepared.price is None or prepared.price_version is None:
        msg = "Datasheet model job has no frozen price"
        raise ConflictError(msg)
    fallback = _OfflineProvider(job, prepared) if prepared.config.provider == "fake" else None
    with provider_session(prepared.config, supplied or fallback) as provider:
        reservation = reserve(
            db,
            BudgetRequest(
                conversation_id=job.id,
                model=request.model,
                input_tokens=sum(segment.tokens for segment in request.segments),
                max_output_tokens=request.max_output_tokens,
                limits=prepared.config.budget,
            ),
            prepared.price_version,
            prepared.price,
        )
        try:
            validate_fence(db, job.id, fence)
        except ConflictError:
            refund(db, reservation.id, "Datasheet shard lease was lost before invocation")
            raise
        started = perf_counter()
        try:
            response = provider.complete(request)
        except Exception:
            _settle(
                db,
                reservation.id,
                request,
                job,
                ModelResponse(stop_reason="provider_error", usage_known=False),
                started,
            )
            raise
        _settle(db, reservation.id, request, job, response, started)
    if response.tool_calls or response.stop_reason in {"length", "max_tokens"}:
        msg = "Datasheet model returned tools or truncated output"
        raise ValidationError(msg)
    return response.content
