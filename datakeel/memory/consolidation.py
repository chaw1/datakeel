# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Deterministic scope-preserving consolidation with archived provenance."""

import unicodedata
from datetime import datetime

from datakeel.core.memory_models import MemoryEntry, MemoryPolicy
from datakeel.memory.retrieval import refreshed

SIMILARITY_THRESHOLD = 0.8


def normalize(text: str) -> str:
    """Fold width, case and repeated whitespace while preserving factual punctuation."""
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


def _bigrams(text: str) -> set[str]:
    return {text[index : index + 2] for index in range(len(text) - 1)}


def _similar(first: MemoryEntry, second: MemoryEntry, *, exact: bool) -> bool:
    if first.dataset_id != second.dataset_id:
        return False
    left, right = normalize(first.content), normalize(second.content)
    if exact or left == right:
        return left == right
    left_pairs, right_pairs = _bigrams(left), _bigrams(right)
    union = left_pairs | right_pairs
    return bool(union) and len(left_pairs & right_pairs) / len(union) >= SIMILARITY_THRESHOLD


def _merge(winner: MemoryEntry, other: MemoryEntry, now: datetime) -> MemoryEntry:
    used = [item for item in (winner.last_used_at, other.last_used_at) if item is not None]
    strength = max(winner.current_strength, other.current_strength)
    return winner.model_copy(
        update={
            "strength": strength,
            "current_strength": strength,
            "reinforced_at": now,
            "last_used_at": max(used) if used else None,
            "source_conversation_ids": sorted(
                set(winner.source_conversation_ids + other.source_conversation_ids)
            ),
            "source_memory_ids": sorted(
                set(winner.source_memory_ids + other.source_memory_ids + [other.id])
            ),
        }
    )


def consolidate(
    entries: list[MemoryEntry], now: datetime, policy: MemoryPolicy
) -> list[MemoryEntry]:
    """Merge exact then similar memories, preserving the strongest representative and sources."""
    result = {item.id: refreshed(item, now, policy) for item in entries}
    active = [item for item in result.values() if not item.archived]
    if len(active) <= policy.max_entries:
        return list(result.values())
    for exact in (True, False):
        kept: list[MemoryEntry] = []
        for entry in sorted(active, key=lambda item: (-item.current_strength, item.id)):
            match = next((item for item in kept if _similar(item, entry, exact=exact)), None)
            if match is None:
                kept.append(entry)
                continue
            merged = _merge(match, entry, now)
            kept[kept.index(match)] = merged
            result[merged.id] = merged
            result[entry.id] = entry.model_copy(update={"archived": True})
        active = kept
    retained = sorted(active, key=lambda item: (-item.current_strength, item.id))
    for entry in retained[policy.max_entries :]:
        result[entry.id] = entry.model_copy(update={"archived": True})
    return sorted(result.values(), key=lambda item: item.id)
