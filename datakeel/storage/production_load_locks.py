# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Serialize each person's load check and new assignments within one project.

A load limit holds only if counting a person's active assignments and inserting the next one
cannot interleave with another transaction doing the same for that person. Claims lock only the
task row they take, so two claims by one person would otherwise both count the same load. Every
path that checks a load takes one transaction-level lock per (project, person) first, in
identity order, and the check itself refuses to count a person whose lock this transaction does
not hold, so a new dispatch path cannot silently skip the step on either database.
"""

import json
from collections.abc import Iterable

from sqlalchemy import event, text
from sqlalchemy.orm import Session, SessionTransaction

_HELD = "datakeel.production_load_locks"


class LoadLockError(RuntimeError):
    """A load was counted without first serializing on that person (a programming error)."""


def lock_people(session: Session, project_id: str, actors: Iterable[str]) -> None:
    """Hold each person's project load lock until the transaction ends, smallest identity first.

    PostgreSQL takes a transaction-level advisory lock in its own key space; SQLite writers
    already hold the database write lock, so only the bookkeeping applies there.
    """
    held: set[tuple[str, str]] = session.info.setdefault(_HELD, set())
    postgres = session.get_bind().dialect.name == "postgresql"
    for actor in sorted(set(actors)):
        if postgres:
            session.execute(
                text(
                    "SELECT pg_advisory_xact_lock("
                    "hashtext('datakeel:production-load:' || current_schema()), hashtext(:key))"
                ),
                {"key": json.dumps([project_id, actor])},
            )
        held.add((project_id, actor))


def require_people_locked(session: Session, project_id: str, actors: Iterable[str]) -> None:
    """Refuse to count a load whose person lock this transaction does not hold."""
    held: set[tuple[str, str]] = session.info.get(_HELD, set())
    missing = sorted(actor for actor in set(actors) if (project_id, actor) not in held)
    if missing:
        message = f"Load counted without the per-person lock for {', '.join(missing)}"
        raise LoadLockError(message)


@event.listens_for(Session, "after_transaction_end")
def _forget_people(session: Session, transaction: SessionTransaction) -> None:
    # Advisory transaction locks end with the outermost transaction; so does the bookkeeping.
    if transaction.parent is None:
        session.info.pop(_HELD, None)
