# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Deterministic consolidation preserves scope, strength and source identities."""

from datetime import timedelta

from datakeel.core.memory_models import MemoryPolicy
from datakeel.memory.consolidation import consolidate, normalize
from datakeel.memory.retrieval import current_strength
from tests.memory.helpers import NOW, entry


def test_consolidate_when_below_limit_does_not_merge_duplicate_entries() -> None:
    """Retention starts only when active entries exceed the configured cap."""
    entries = [entry("a"), entry("b")]
    assert consolidate(entries, NOW, MemoryPolicy(max_entries=2)) == entries
    assert normalize("  \uff32evenue\n METRIC  ") == "revenue metric"


def test_consolidate_when_exact_duplicates_merge_strongest_and_source_unions() -> None:
    """Archive absorbed entries while keeping the strongest representative's original identity."""
    first = entry("a", "Revenue  Metric").model_copy(
        update={"source_conversation_ids": ["first"], "last_used_at": NOW}
    )
    second = entry("b", "revenue metric").model_copy(
        update={
            "strength": 2,
            "source_conversation_ids": ["second"],
            "source_memory_ids": ["older"],
            "last_used_at": NOW - timedelta(days=1),
        }
    )
    result = consolidate([first, second], NOW, MemoryPolicy(max_entries=1))
    winner = next(item for item in result if not item.archived)
    assert winner.id == "b"
    assert winner.strength == 2
    assert winner.source_conversation_ids == ["first", "second"]
    assert winner.source_memory_ids == ["a", "older"]
    assert winner.last_used_at == NOW
    assert next(item for item in result if item.id == "a").archived


def test_consolidate_when_near_duplicates_share_bigrams_merges_deterministically() -> None:
    """Input ordering cannot change a near-duplicate cluster's winner or provenance."""
    entries = [
        entry("b", "revenue metric excludes refunded orders."),
        entry("a", "revenue metric excludes refunded orders"),
    ]
    policy = MemoryPolicy(max_entries=1)
    result = consolidate(entries, NOW, policy)
    assert result == consolidate(list(reversed(entries)), NOW, policy)
    assert [item.id for item in result if not item.archived] == ["a"]
    assert result[0].source_memory_ids == ["b"]
    assert consolidate(result, NOW, policy) == result


def test_consolidate_when_scopes_differ_never_merges_and_archives_weakest() -> None:
    """Scope boundaries survive identical wording, and decayed strength controls eviction."""
    global_entry = entry("a")
    scoped = entry("b").model_copy(update={"dataset_id": "dataset", "strength": 2})
    weak = entry("c", "unrelated retention note").model_copy(
        update={"reinforced_at": NOW - timedelta(days=70)}
    )
    result = consolidate([weak, scoped, global_entry], NOW, MemoryPolicy(max_entries=2))
    assert [item.id for item in result if not item.archived] == ["a", "b"]
    assert all(not item.source_memory_ids for item in result)


def test_consolidate_when_single_character_texts_differ_does_not_merge_empty_bigrams() -> None:
    """An empty similarity denominator cannot turn unrelated short notes into duplicates."""
    result = consolidate([entry("a", "一"), entry("b", "二")], NOW, MemoryPolicy(max_entries=1))
    assert result[0].source_memory_ids == []


def test_consolidate_when_old_strength_decayed_keeps_current_maximum_without_amplification() -> (
    None
):
    """A historical base strength of three cannot outrank a fresher currently stronger entry."""
    old = entry("a").model_copy(update={"strength": 3, "reinforced_at": NOW - timedelta(days=28)})
    fresh = entry("b")
    policy = MemoryPolicy(max_entries=1)
    winner = next(item for item in consolidate([old, fresh], NOW, policy) if not item.archived)
    assert winner.id == "b"
    assert winner.strength == 1
    assert current_strength(winner, NOW + timedelta(days=14), policy) == 0.5
