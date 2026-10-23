# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Fixed-clock generated memory fixtures."""

from datetime import UTC, datetime

from datakeel.core.memory_models import MemoryEntry

NOW = datetime(2026, 10, 24, 10, tzinfo=UTC)


def entry(identifier: str, content: str = "revenue metric definition") -> MemoryEntry:
    """Build a typed memory without persistence or ambient clock dependencies."""
    return MemoryEntry(id=identifier, content=content, created_at=NOW, reinforced_at=NOW)
