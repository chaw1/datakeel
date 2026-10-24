# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Normalize UTF-8 documents and split them without losing original offsets."""

import re
import unicodedata

from datakeel.core.kg_models import TextBlock


def decode_text(content: bytes) -> str:
    """Decode strictly as UTF-8 and establish the NFC coordinate system."""
    return unicodedata.normalize("NFC", content.decode("utf-8"))


def normalize_name(name: str) -> str:
    """Apply the product identity rule independently of benchmark alignment."""
    return " ".join(unicodedata.normalize("NFKC", name).strip().lower().split())


def chunk_text(text: str, size: int, overlap: int = 0) -> tuple[TextBlock, ...]:
    """Prefer paragraph or sentence boundaries, hard-splitting only overlong sentences."""
    if size <= 0 or overlap < 0 or overlap >= size:
        msg = "Chunk size must be positive and overlap must be smaller than size"
        raise ValueError(msg)
    boundaries = [
        match.end()
        for match in re.finditer(r"\n\s*\n|[.!?](?:\s+|$)|[\u3002\uff01\uff1f]\s*", text)
    ]
    blocks: list[TextBlock] = []
    start = 0
    while start < len(text):
        limit = min(start + size, len(text))
        candidates = [end for end in boundaries if start + overlap < end <= limit]
        end = max(candidates) if candidates and limit < len(text) else limit
        blocks.append(TextBlock(text=text[start:end], start=start, end=end))
        if end == len(text):
            break
        start = end - overlap
    return tuple(blocks)
