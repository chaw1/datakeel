# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Fixed-clock generated memory fixtures."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from functools import partial
from typing import TYPE_CHECKING

from datakeel.core.memory_models import MemoryEntry
from datakeel.memory.service import reinforce_memories, select_memories

if TYPE_CHECKING:
    import pytest

NOW = datetime(2026, 10, 24, 10, tzinfo=UTC)


@dataclass
class MemoryClock:
    """Keep model memory reads and writes on one explicitly controlled test clock."""

    now: datetime = NOW

    def __call__(self) -> datetime:
        """Return the fixture instant without consulting ambient wall time."""
        return self.now


def freeze_memory_clock(monkeypatch: pytest.MonkeyPatch) -> MemoryClock:
    """Bind actual model selection and reinforcement to the same controllable clock."""
    clock = MemoryClock()
    monkeypatch.setattr(
        "datakeel.agent.metering.select_memories", partial(select_memories, clock=clock)
    )
    monkeypatch.setattr(
        "datakeel.agent.metering.reinforce_memories", partial(reinforce_memories, clock=clock)
    )
    return clock


def entry(identifier: str, content: str = "revenue metric definition") -> MemoryEntry:
    """Build a typed memory without persistence or ambient clock dependencies."""
    return MemoryEntry(id=identifier, content=content, created_at=NOW, reinforced_at=NOW)
