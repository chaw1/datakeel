# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Generate stable 64-bit text simhashes without modifying source content."""

import hashlib
import string
import unicodedata
from collections import Counter

HASH_BITS = 64
FEATURE_WIDTH = 3
_ZERO_WIDTH = frozenset("\u200b\u200c\u200d\u2060\ufeff")


def normalize_text(text: str) -> str:
    """Fold Unicode compatibility and case, removing whitespace and punctuation."""
    folded = unicodedata.normalize("NFKC", unicodedata.normalize("NFKC", text).casefold())
    characters = "".join(
        character
        for character in folded
        if not character.isspace()
        and character not in _ZERO_WIDTH
        and character not in string.punctuation
        and not unicodedata.category(character).startswith("P")
    )
    return unicodedata.normalize("NFKC", characters)


def simhash(text: str) -> int | None:
    """Vote over counted character trigrams, omitting content with no normalized characters."""
    normalized = normalize_text(text)
    if not normalized:
        return None
    features = Counter(
        normalized[index : index + FEATURE_WIDTH]
        for index in range(max(1, len(normalized) - FEATURE_WIDTH + 1))
    )
    votes = [0] * HASH_BITS
    for feature, weight in sorted(features.items()):
        fingerprint = int.from_bytes(hashlib.sha256(feature.encode("utf-8")).digest()[:8], "big")
        for bit in range(HASH_BITS):
            votes[bit] += weight if fingerprint & (1 << bit) else -weight
    return sum(1 << bit for bit, vote in enumerate(votes) if vote > 0)
