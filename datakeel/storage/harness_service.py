# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Settle exactly one trace with each reservation and report persisted costs."""

from collections import defaultdict
from decimal import Decimal
from typing import Literal

from sqlalchemy import select

from datakeel.core.errors import ConflictError, NotFoundError
from datakeel.core.harness_models import CostSummary, ModelCallTrace, TraceInput
from datakeel.core.harness_pricing import ModelPrice, nanos_to_usd, usage_cost, usd_to_nanos
from datakeel.core.models import new_id, utcnow
from datakeel.storage.budget_accounts import lock_budget, release_account, reserved_accounts
from datakeel.storage.budget_rows import BudgetAccountRow, BudgetReservationRow
from datakeel.storage.database import Database
from datakeel.storage.harness_rows import ModelCallTraceRow


def settle(db: Database, reservation_id: str, trace: TraceInput) -> ModelCallTrace:
    """Persist observed or conservatively unknown charges before reporting budget overruns."""
    with db.session() as session:
        lock_budget(db, session)
        row = session.get(BudgetReservationRow, reservation_id)
        if row is None:
            msg = "Budget reservation not found"
            raise NotFoundError(msg)
        existing = session.scalar(
            select(ModelCallTraceRow).where(ModelCallTraceRow.reservation_id == reservation_id)
        )
        if existing is not None:
            result = ModelCallTrace.model_validate(existing.payload)
            if (
                TraceInput.model_validate(result.model_dump(include=set(TraceInput.model_fields)))
                != trace
            ):
                msg = "Reservation already settled with different trace content"
                raise ConflictError(msg)
            return result
        if row.status != "RESERVED":
            msg = "Reservation is not outstanding"
            raise ConflictError(msg)
        if row.conversation_id != trace.conversation_id or row.model != trace.model:
            msg = "Trace does not match its reserved conversation and model"
            raise ConflictError(msg)
        result = _account_trace(row, trace, reserved_accounts(session, row))
        session.add(
            ModelCallTraceRow(
                id=result.id,
                reservation_id=row.id,
                conversation_id=row.conversation_id,
                model=row.model,
                day=row.day,
                cost_nanos=usd_to_nanos(result.cost_usd),
                payload=result.model_dump(mode="json"),
            )
        )
        session.commit()
        return result


def _account_trace(
    row: BudgetReservationRow, trace: TraceInput, accounts: list[BudgetAccountRow]
) -> ModelCallTrace:
    unknown = trace.billing_status == "unknown"
    tokens = row.tokens if unknown else trace.usage.input_tokens + trace.usage.output_tokens
    cost = (
        row.cost_nanos if unknown else usage_cost(ModelPrice.model_validate(row.price), trace.usage)
    )
    for account in accounts:
        release_account(account, row)
        account.used_tokens += tokens
        account.spent_nanos += cost
    exceeded = any(
        account.used_tokens + account.reserved_tokens > account.token_limit
        or account.spent_nanos + account.reserved_nanos > account.usd_limit_nanos
        for account in accounts
    )
    row.status = "SETTLED"
    return ModelCallTrace(
        **trace.model_dump(),
        id=new_id(),
        reservation_id=row.id,
        cost_usd=nanos_to_usd(cost),
        price_version=row.price_version,
        created_at=utcnow(),
        accounted_tokens=tokens,
        budget_exceeded=exceeded,
    )


def list_traces(db: Database, conversation_id: str | None = None) -> list[ModelCallTrace]:
    """Return complete replayable call measurements in stable occurrence order."""
    with db.session() as session:
        query = select(ModelCallTraceRow).order_by(
            ModelCallTraceRow.created_at, ModelCallTraceRow.id
        )
        if conversation_id is not None:
            query = query.where(ModelCallTraceRow.conversation_id == conversation_id)
        return [ModelCallTrace.model_validate(row.payload) for row in session.scalars(query)]


def summarize_costs(
    db: Database, group_by: Literal["conversation", "day", "model"] = "conversation"
) -> list[CostSummary]:
    """Aggregate observations and separately identify unknown conservative charges."""
    groups: dict[str, list[ModelCallTrace]] = defaultdict(list)
    for trace in list_traces(db):
        key = {
            "conversation": trace.conversation_id,
            "day": trace.created_at.date().isoformat(),
            "model": trace.model,
        }[group_by]
        groups[key].append(trace)
    return [
        CostSummary(
            key=key,
            group_by=group_by,
            calls=len(values),
            input_tokens=sum(value.usage.input_tokens for value in values),
            output_tokens=sum(value.usage.output_tokens for value in values),
            cache_read_tokens=sum(value.usage.cache_read_tokens for value in values),
            cache_write_tokens=sum(value.usage.cache_write_tokens for value in values),
            cost_usd=sum((value.cost_usd for value in values), start=Decimal(0)),
            unknown_calls=sum(value.billing_status == "unknown" for value in values),
            unknown_cost_usd=sum(
                (value.cost_usd for value in values if value.billing_status == "unknown"),
                start=Decimal(0),
            ),
        )
        for key, values in sorted(groups.items())
    ]
