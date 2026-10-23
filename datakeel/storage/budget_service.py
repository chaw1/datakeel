# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Reserve model-call bounds before execution and refund unmade calls exactly once."""

from datakeel.core.errors import BudgetError, ConflictError, NotFoundError
from datakeel.core.harness_models import BudgetRequest, BudgetReservation
from datakeel.core.harness_pricing import ModelPrice, nanos_to_usd, reservation_cost
from datakeel.core.models import utcnow
from datakeel.storage.budget_accounts import (
    accounts_for,
    lock_budget,
    release_account,
    reserved_accounts,
)
from datakeel.storage.budget_rows import BudgetReservationRow
from datakeel.storage.database import Database


def reservation_view(row: BudgetReservationRow) -> BudgetReservation:
    """Convert the internal accounting row into a frozen reservation handle."""
    return BudgetReservation.model_validate(
        {
            "id": row.id,
            "conversation_id": row.conversation_id,
            "model": row.model,
            "day": row.day,
            "tokens": row.tokens,
            "cost_usd": nanos_to_usd(row.cost_nanos),
            "status": row.status,
        }
    )


def reserve(
    db: Database, request: BudgetRequest, price_version: str, price: ModelPrice
) -> BudgetReservation:
    """Atomically reserve both limits, persisting a rejected attempt before raising."""
    tokens = request.input_tokens + request.max_output_tokens
    cost = reservation_cost(price, request.input_tokens, request.max_output_tokens)
    day = utcnow().date().isoformat()
    with db.session() as session:
        lock_budget(db, session)
        accounts = accounts_for(session, request, day)
        exceeded = any(
            row.used_tokens + row.reserved_tokens + tokens > row.token_limit
            or row.spent_nanos + row.reserved_nanos + cost > row.usd_limit_nanos
            for row in accounts
        )
        reservation = BudgetReservationRow(
            conversation_id=request.conversation_id,
            model=request.model,
            day=day,
            tokens=tokens,
            cost_nanos=cost,
            status="REJECTED" if exceeded else "RESERVED",
            price=price.model_dump(mode="json"),
            price_version=price_version,
            reason="Budget exceeded" if exceeded else "",
        )
        session.add(reservation)
        if not exceeded:
            for row in accounts:
                row.reserved_tokens += tokens
                row.reserved_nanos += cost
        session.commit()
        result = reservation_view(reservation)
    if exceeded:
        msg = "Persistent conversation or daily token/cost budget exceeded"
        raise BudgetError(msg)
    return result


def refund(db: Database, reservation_id: str, reason: str) -> None:
    """Idempotently release a call that never reached the provider."""
    with db.session() as session:
        lock_budget(db, session)
        row = session.get(BudgetReservationRow, reservation_id)
        if row is None:
            msg = "Budget reservation not found"
            raise NotFoundError(msg)
        if row.status == "REFUNDED":
            return
        if row.status != "RESERVED":
            msg = "Only an outstanding reservation can be refunded"
            raise ConflictError(msg)
        for account in reserved_accounts(session, row):
            release_account(account, row)
        row.status, row.reason = "REFUNDED", reason
        session.commit()
