# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Lock and update persistent conversation and global daily budget accounts."""

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from datakeel.core.harness_models import BudgetAccount, BudgetRequest
from datakeel.core.harness_pricing import nanos_to_usd, usd_to_nanos
from datakeel.storage.budget_rows import BudgetAccountRow, BudgetReservationRow
from datakeel.storage.database import Database


def lock_budget(db: Database, session: Session) -> None:
    """Serialize creation and reservation, including previously unseen daily keys."""
    db.lock_writes(session)
    if not db.sqlite:
        session.execute(
            text("SELECT pg_advisory_xact_lock(hashtext('datakeel:budget:' || current_schema()))")
        )


def accounts_for(session: Session, request: BudgetRequest, day: str) -> list[BudgetAccountRow]:
    """Get both scopes, allowing tighter limits but never a client-side increase."""
    limits = request.limits
    scopes = [
        (
            f"conversation:{request.conversation_id}",
            limits.conversation_tokens,
            limits.conversation_usd,
        ),
        (f"day:{day}", limits.daily_tokens, limits.daily_usd),
    ]
    rows: list[BudgetAccountRow] = []
    for key, tokens, usd in scopes:
        row = session.get(BudgetAccountRow, key)
        if row is None:
            row = BudgetAccountRow(key=key, token_limit=tokens, usd_limit_nanos=usd_to_nanos(usd))
            session.add(row)
            session.flush()
        row.token_limit = min(row.token_limit, tokens)
        row.usd_limit_nanos = min(row.usd_limit_nanos, usd_to_nanos(usd))
        rows.append(row)
    return rows


def reserved_accounts(
    session: Session, reservation: BudgetReservationRow
) -> list[BudgetAccountRow]:
    """Load the exact original UTC day even when a call crosses midnight."""
    keys = [f"conversation:{reservation.conversation_id}", f"day:{reservation.day}"]
    return list(session.scalars(select(BudgetAccountRow).where(BudgetAccountRow.key.in_(keys))))


def release_account(row: BudgetAccountRow, reservation: BudgetReservationRow) -> None:
    """Remove a reservation once after either settlement or explicit refund."""
    row.reserved_tokens -= reservation.tokens
    row.reserved_nanos -= reservation.cost_nanos


def list_accounts(db: Database) -> list[BudgetAccount]:
    """Expose typed balances for diagnostics and restart verification."""
    with db.session() as session:
        return [
            BudgetAccount(
                key=row.key,
                token_limit=row.token_limit,
                usd_limit=nanos_to_usd(row.usd_limit_nanos),
                used_tokens=row.used_tokens,
                reserved_tokens=row.reserved_tokens,
                spent_usd=nanos_to_usd(row.spent_nanos),
                reserved_usd=nanos_to_usd(row.reserved_nanos),
            )
            for row in session.scalars(select(BudgetAccountRow).order_by(BudgetAccountRow.key))
        ]
