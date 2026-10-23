# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Upgrade legacy conversation rows without exposing or rotating their sentinels."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import text

from datakeel.core.agent_models import ConversationCreate
from datakeel.storage import conversation_store
from datakeel.storage.conversation_secrets import get_canary

if TYPE_CHECKING:
    from datakeel.storage.database import Database


def test_old_table_gains_nullable_secret_and_assigns_it_once(unmigrated_db: Database) -> None:
    """Additive migration repairs a pre-canary schema and retains existing conversations."""
    db = unmigrated_db
    db.migrate()
    first = conversation_store.create(db, ConversationCreate())
    with db.engine.begin() as connection:
        connection.execute(text("ALTER TABLE conversations DROP COLUMN canary"))
    db.migrate()
    canary = get_canary(db, first.id)
    assert get_canary(db, first.id) == canary
    assert canary.startswith("dkc_")
    assert canary not in conversation_store.get(db, first.id).model_dump_json()
    second = conversation_store.create(db, ConversationCreate())
    assert get_canary(db, second.id) != canary
