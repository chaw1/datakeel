# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Offline BM25 retrieval, lazy decay and bounded data-only serialization."""

import json
import math
import re
from collections import Counter
from datetime import datetime

from datakeel.core.context_tokens import estimate_tokens
from datakeel.core.envelopes import MARKER
from datakeel.core.memory_models import MemoryEntry, MemoryPolicy, MemorySelection

TOKEN_PATTERN = re.compile(r"[\u3400-\u9fff\uf900-\ufaff\U00020000-\U0002fa1f]+|[a-z]+")
TOP_K = 3
SEGMENT_LIMIT = 1200
SEGMENT_OVERHEAD = 16
MINIMUM_OVERLAP = 2


def tokenize(text: str) -> list[str]:
    """Use adjacent Chinese character pairs and lowercase English words."""
    result: list[str] = []
    for match in TOKEN_PATTERN.findall(text.lower()):
        if match.isascii():
            result.append(match)
        else:
            result.extend(match[index : index + 2] for index in range(len(match) - 1))
    return result


def current_strength(entry: MemoryEntry, now: datetime, policy: MemoryPolicy) -> float:
    """Apply the fixed floor and exponential half-life from the last reinforcement."""
    days = max(0.0, (now - entry.reinforced_at).total_seconds() / 86400)
    return max(0.05, entry.strength * 2 ** (-days / policy.half_life_days))


def refreshed(entry: MemoryEntry, now: datetime, policy: MemoryPolicy) -> MemoryEntry:
    """Compute a current view without mutating the last reinforcement timestamp."""
    return entry.model_copy(update={"current_strength": current_strength(entry, now, policy)})


def reinforced(entry: MemoryEntry, now: datetime, policy: MemoryPolicy) -> MemoryEntry:
    """Increase only a selected entry, restarting its half-life at the injected clock."""
    strength = min(3.0, current_strength(entry, now, policy) + 0.5)
    return entry.model_copy(
        update={
            "strength": strength,
            "current_strength": strength,
            "reinforced_at": now,
            "last_used_at": now,
        }
    )


def _score(query: set[str], tokens: Counter[str], corpus: list[Counter[str]]) -> float:
    average = sum(sum(item.values()) for item in corpus) / len(corpus)
    length = sum(tokens.values())
    result = 0.0
    for token in sorted(query.intersection(tokens)):
        frequency = tokens[token]
        documents = sum(token in item for item in corpus)
        idf = math.log(1 + (len(corpus) - documents + 0.5) / (documents + 0.5))
        result += idf * frequency * 2.2 / (frequency + 1.2 * (0.25 + 0.75 * length / average))
    return result


def _serialize(entries: list[MemoryEntry]) -> str:
    return json.dumps(
        [MARKER, "memory", [[item.id, item.content] for item in entries]],
        ensure_ascii=False,
        separators=(",", ":"),
    )


def select_entries(entries: list[MemoryEntry], query: str) -> MemorySelection:
    """Rank by BM25 times current strength, then recency and stable identity."""
    active = [item for item in entries if not item.archived]
    corpus = [Counter(tokenize(item.content)) for item in active]
    query_tokens = set(tokenize(query))
    ranked: list[tuple[float, float, str, MemoryEntry]] = []
    for entry, tokens in zip(active, corpus, strict=True):
        if len(query_tokens.intersection(tokens)) < MINIMUM_OVERLAP:
            continue
        score = _score(query_tokens, tokens, corpus) * entry.current_strength
        if score > 0:
            last_used = entry.last_used_at.timestamp() if entry.last_used_at else -math.inf
            ranked.append((-score, -last_used, entry.id, entry))
    selected = [item[3] for item in sorted(ranked)[:TOP_K]]
    while selected and estimate_tokens(_serialize(selected)) + SEGMENT_OVERHEAD > SEGMENT_LIMIT:
        selected.pop()
    return MemorySelection(entries=selected, text=_serialize(selected) if selected else "")
