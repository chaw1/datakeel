# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""One explicit persistence entry point shared by application and test initializers."""

from __future__ import annotations

from datakeel.persistence.canonical import canonical_schema
from datakeel.persistence.legacy import schema_contributions
from datakeel.storage.database import Database
from datakeel.versioning import initialize

__all__ = ["Database", "migrate"]


def migrate(database: Database) -> None:
    """Initialize empty demo/fixture stores; validate current SQLite restarts."""
    if database.sqlite:
        initialize(database)
    else:
        database.migrate(schema_contributions(), canonical=canonical_schema())
