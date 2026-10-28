# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Deterministic Unicode-aware 64-bit text similarity without model calls."""

import hashlib
import unicodedata
from collections import Counter


def normalize_text(text: str) -> str:
    """Ignore Unicode compatibility, case, whitespace and punctuation differences."""
    return "".join(
        character
        for character in unicodedata.normalize("NFKC", text).casefold()
        if not character.isspace() and not unicodedata.category(character).startswith("P")
    )


def simhash(text: str) -> int | None:
    """Hash weighted character trigrams; return no signal for empty normalized content."""
    normalized = normalize_text(text)
    if not normalized:
        return None
    tokens = Counter(normalized[index : index + 3] for index in range(max(1, len(normalized) - 2)))
    weights = [0] * 64
    for token, count in sorted(tokens.items()):
        value = int.from_bytes(hashlib.sha256(token.encode()).digest()[:8])
        for bit in range(64):
            weights[bit] += count if value & (1 << bit) else -count
    return sum(1 << bit for bit, weight in enumerate(weights) if weight > 0)
