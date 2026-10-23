# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Provider-neutral token bounds and exact segment allocation."""

from datakeel.core.agent_models import ContextSegment
from datakeel.core.harness_models import TokenSegment


def estimate_tokens(text: str) -> int:
    """Use a conservative UTF-8 byte bound before provider-specific token usage exists."""
    return max(1, len(text.encode("utf-8")))


def allocate_tokens(segments: list[ContextSegment], input_tokens: int) -> list[TokenSegment]:
    """Allocate authoritative provider input proportionally with an exact integer sum."""
    weights = sum(segment.tokens for segment in segments)
    remaining = input_tokens
    result: list[TokenSegment] = []
    for index, segment in enumerate(segments):
        tokens = (
            remaining
            if index == len(segments) - 1
            else input_tokens * segment.tokens // max(1, weights)
        )
        result.append(
            TokenSegment(name=segment.name, tokens=tokens, stable=segment.kind == "stable")
        )
        remaining -= tokens
    return result
