# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Protect authoritative runtime ownership independently of legacy public view fields."""

import pytest

from datakeel.core.errors import AuthorizationError
from datakeel.storage.database import Database
from datakeel.storage.identity_sessions import (
    bind_session_actor,
    require_session_actor,
    session_actor,
)


def test_runtime_binding_is_idempotent_and_cannot_be_replaced(db: Database) -> None:
    """The first server owner remains authoritative over repeated transport requests."""
    bind_session_actor(db, "session", "alice")
    bind_session_actor(db, "session", "alice")
    assert session_actor(db, "session") == "alice"
    require_session_actor(db, "session", "alice")
    with pytest.raises(AuthorizationError):
        bind_session_actor(db, "session", "other")
    with pytest.raises(AuthorizationError):
        require_session_actor(db, "session", "other")


def test_legacy_unbound_session_keeps_local_ownership(db: Database) -> None:
    """Old checkpoints remain recoverable by the original local actor."""
    assert session_actor(db, "legacy") == "local"
    require_session_actor(db, "legacy", "local")
    with pytest.raises(AuthorizationError):
        require_session_actor(db, "legacy", "another")
