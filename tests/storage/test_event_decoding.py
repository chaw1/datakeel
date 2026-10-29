# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Authoritative event readers preserve complete payloads and legacy Unicode."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest
from pydantic import ValidationError
from sqlalchemy import select

from datakeel.core.models import AssetRef, LineageEvent
from datakeel.storage.database import EventRow
from datakeel.storage.events import all_events, append_event

if TYPE_CHECKING:
    from datakeel.storage.database import Database


@pytest.mark.parametrize("message", ["école/🙂/\x00", "\ud800"])
def test_complete_events_preserve_nested_payload_and_unicode(db: Database, message: str) -> None:
    """Retain every event field, including strings accepted by the legacy JSON reader."""
    event = LineageEvent(
        event_id="attributed-event",
        idempotency_key="attributed-event",
        event_type="CUSTOM",
        inputs=[AssetRef(asset_id="in", namespace="custom", version="v1")],
        outputs=[AssetRef(asset_type="column", asset_id="out", display_name="列")],
        operator="snapshot",
        on_behalf_of="fixture-user",
        source_module="catalog",
        source_ref="fixture://catalog",
        params={
            "objects": [{"name": message, "values": [None, False, 10**60, 1.0 / 3.0]}],
            "links": [{"source": "in", "target": "out", "kind": "derived"}],
        },
        run_state="FAILED",
        occurred_at=datetime(2026, 10, 28, 3, 4, 5, 123456, tzinfo=UTC),
        quality={"checks": [{"passed": False, "message": message}], "ratio": -0.0},
    )
    with db.session() as session:
        append_event(session, event)
        session.commit()
        legacy = [
            LineageEvent.model_validate(payload)
            for payload in session.scalars(select(EventRow.payload))
        ]
        assert all_events(session) == legacy == [event]


def test_event_reader_preserves_validation_errors(db: Database) -> None:
    """Reject invalid domain fields and unknown fields without suppressing their errors."""
    with db.session() as session:
        session.add(
            EventRow(
                event_id="invalid",
                idempotency_key="invalid",
                payload={"idempotency_key": "invalid", "operator": None, "unknown": True},
            )
        )
        session.commit()
        with pytest.raises(ValidationError) as caught:
            all_events(session)
        assert {(error["loc"], error["type"]) for error in caught.value.errors()} == {
            (("operator",), "string_type"),
            (("unknown",), "extra_forbidden"),
        }


def test_event_reader_empty_store(db: Database) -> None:
    """Reading a fresh event stream returns no synthetic facts."""
    with db.session() as session:
        assert all_events(session) == []
