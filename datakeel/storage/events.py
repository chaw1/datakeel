# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Idempotent persistence for the authoritative append-only event stream."""

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from datakeel.core.models import LineageEvent
from datakeel.storage.database import EventRow


def append_event(session: Session, event: LineageEvent) -> bool:
    """Append an event once, returning whether its idempotency key was new."""
    factory = sqlite_insert if session.get_bind().dialect.name == "sqlite" else pg_insert
    statement = (
        factory(EventRow)
        .values(
            event_id=event.event_id,
            idempotency_key=event.idempotency_key,
            payload=event.model_dump(mode="json"),
        )
        .on_conflict_do_nothing(index_elements=["idempotency_key"])
        .returning(EventRow.event_id)
    )
    return session.execute(statement).scalar_one_or_none() is not None


def all_events(session: Session) -> list[LineageEvent]:
    """Read authoritative event payloads as immutable domain models."""
    return [LineageEvent.model_validate(row.payload) for row in session.scalars(select(EventRow))]
