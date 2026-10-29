# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Apply production state counters at commit time, in one global lock order.

Every task transition changes a project counter and a package counter. Those few rows are the
hottest in a busy project, so a transaction records its deltas and writes them just before it
commits: the row locks are held only for the commit itself, the rows are always locked sorted by
scope and state (no deadlocks between opposite transitions or multi-task transactions), and a
transition that is undone in the same transaction writes nothing. Inside a savepoint the change
is written at once, so rolling the savepoint back also rolls the counters back. Nothing reads
these counters inside the transaction that changes them; reads use separate sessions.
"""

from collections import Counter
from collections.abc import Iterable

from sqlalchemy import event, update
from sqlalchemy.orm import Session, SessionTransaction

from datakeel.storage.production_rows import ProductionSummaryRow

_DELTAS = "datakeel.production_counter_deltas"


def defer_counter_change(
    session: Session, scopes: Iterable[str], previous: str, state: str
) -> None:
    """Move one task between state counters of each scope when the transaction commits."""
    deltas: Counter[tuple[str, str]] = Counter()
    for scope in scopes:
        deltas[scope, previous] -= 1
        deltas[scope, state] += 1
    if session.in_nested_transaction():
        _write(session, deltas)
        return
    session.info.setdefault(_DELTAS, Counter()).update(deltas)


def _write(session: Session, deltas: Counter[tuple[str, str]]) -> None:
    for (scope, state), delta in sorted(deltas.items()):
        if delta:
            session.execute(
                update(ProductionSummaryRow)
                .where(ProductionSummaryRow.scope_id == scope, ProductionSummaryRow.state == state)
                .values(count=ProductionSummaryRow.count + delta)
            )


@event.listens_for(Session, "before_commit")
def _apply_counter_changes(session: Session) -> None:
    # Savepoint releases also fire before_commit; only the outermost commit writes the deltas.
    if session.in_nested_transaction():
        return
    deltas: Counter[tuple[str, str]] | None = session.info.pop(_DELTAS, None)
    if deltas:
        _write(session, deltas)


@event.listens_for(Session, "after_transaction_end")
def _discard_counter_changes(session: Session, transaction: SessionTransaction) -> None:
    # A rolled-back or closed top-level transaction drops its unapplied deltas.
    if transaction.parent is None:
        session.info.pop(_DELTAS, None)
