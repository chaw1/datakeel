# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Record billed label-draft calls as settled traces so the cost summary includes them."""

from collections.abc import Sequence
from decimal import Decimal

from sqlalchemy.orm import Session

from datakeel.core.harness_models import ModelCallTrace, TokenSegment, TokenUsage
from datakeel.core.harness_pricing import ModelPrice, nanos_to_usd, usd_to_nanos
from datakeel.core.label_guidelines import DraftCall
from datakeel.core.models import new_id, utcnow
from datakeel.storage.budget_rows import BudgetReservationRow
from datakeel.storage.harness_rows import ModelCallTraceRow

PRICE_VERSION = "label-draft-profile"


def _price(call: DraftCall) -> ModelPrice:
    rate_in, rate_out = Decimal(str(call.input_price)), Decimal(str(call.output_price))
    return ModelPrice(
        model=call.model,
        provider="openai",
        input=rate_in,
        output=rate_out,
        cache_read=rate_in,
        cache_write=rate_in,
        source="label draft profile",
    )


def _trace(
    plan_id: str, conversation: str | None, call: DraftCall, turn: int, reservation: str
) -> ModelCallTrace:
    unknown = call.billing == "unknown"
    usage = (
        TokenUsage()
        if unknown
        else TokenUsage(input_tokens=call.input_tokens, output_tokens=call.output_tokens)
    )
    return ModelCallTrace(
        conversation_id=plan_id,
        accounting_conversation_id=conversation,
        turn=turn,
        model=call.model,
        provider="openai",
        segments=[TokenSegment(name="label_draft", tokens=usage.input_tokens)],
        usage=usage,
        latency_ms=0,
        stop_reason=call.stop_reason or call.purpose,
        tool_calls=0,
        billing_status=call.billing,
        call_type="extraction",
        agent_path="label_drafts",
        id=new_id(),
        reservation_id=reservation,
        cost_usd=nanos_to_usd(usd_to_nanos(Decimal(str(call.cost_usd)))),
        price_version=PRICE_VERSION,
        created_at=utcnow(),
        accounted_tokens=call.input_tokens + call.output_tokens,
    )


def record_draft_calls(
    session: Session, plan_id: str, conversation: str | None, calls: Sequence[DraftCall]
) -> None:
    """Add one settled reservation and one trace per billed call, in the caller's transaction.

    The plan is the trace's conversation; the chat that planned it, if any, is billed for it.
    """
    day = utcnow().date().isoformat()
    for turn, call in enumerate(calls, start=1):
        cost = usd_to_nanos(Decimal(str(call.cost_usd)))
        reservation = BudgetReservationRow(
            id=new_id(),
            conversation_id=conversation or plan_id,
            model=call.model,
            day=day,
            tokens=call.input_tokens + call.output_tokens,
            cost_nanos=cost,
            status="SETTLED",
            price=_price(call).model_dump(mode="json"),
            price_version=PRICE_VERSION,
            reason=f"label draft {call.purpose}",
        )
        trace = _trace(plan_id, conversation, call, turn, reservation.id)
        session.add(reservation)
        session.add(
            ModelCallTraceRow(
                id=trace.id,
                reservation_id=reservation.id,
                conversation_id=trace.conversation_id,
                accounting_conversation_id=conversation or plan_id,
                agent_path=trace.agent_path,
                depth=0,
                parent_tool_call_id=None,
                model=call.model,
                day=day,
                cost_nanos=cost,
                payload=trace.model_dump(mode="json"),
            )
        )
