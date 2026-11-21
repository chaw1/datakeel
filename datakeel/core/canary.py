# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Short per-conversation sentinels and deterministic output leak detection."""

import secrets
from collections.abc import Iterator, Sequence

from pydantic import JsonValue

from datakeel.core.agent_models import ModelResponse

PREFIX = "dkc_"
MIN_FRAGMENT = 16
HOLD_NON_WHITESPACE = len(PREFIX) + 24


class CanaryStreamBuffer:
    """Release safe prefixes while retaining enough text to catch split sentinel leaks."""

    def __init__(self, canaries: Sequence[str]) -> None:
        """Keep stream-local state and a stable set of active conversation secrets."""
        self._canaries = tuple(canary for canary in canaries if canary)
        self._buffer = ""
        self.emitted = 0
        self.leaked = False

    def push(self, chunk: str) -> str:
        """Inspect accumulated text before releasing anything outside the holdback window."""
        if self.leaked or not chunk:
            return ""
        self._buffer += chunk
        if any(is_leak(canary, self._buffer) for canary in self._canaries):
            self.leaked = True
            return ""
        boundary, remaining = len(self._buffer), HOLD_NON_WHITESPACE
        while boundary and remaining:
            boundary -= 1
            remaining -= not self._buffer[boundary].isspace()
        safe = self._buffer[self.emitted : boundary]
        self.emitted = max(self.emitted, boundary)
        return safe

    def finish(self) -> str:
        """Flush the unsent tail only after a final complete-output leak check."""
        if self.leaked or any(is_leak(canary, self._buffer) for canary in self._canaries):
            self.leaked = True
            return ""
        tail = self._buffer[self.emitted :]
        self.emitted = len(self._buffer)
        return tail


def generate_canary() -> str:
    """Use 96 random bits, kept outside public conversation payloads."""
    return PREFIX + secrets.token_hex(12)


def canary_instruction(canary: str) -> str:
    """Keep the variable sentinel after the shared stable prefix."""
    return f"Secret; never output: {canary}"


def is_leak(canary: str, text: str) -> bool:
    """Reject full or contiguous 16-character random fragments, ignoring case and whitespace."""
    normalized = "".join(text.split()).casefold()
    random = canary.removeprefix(PREFIX).casefold()
    return bool(canary) and (
        canary.casefold() in normalized
        or any(
            random[index : index + MIN_FRAGMENT] in normalized
            for index in range(len(random) - MIN_FRAGMENT + 1)
        )
    )


def _strings(value: JsonValue) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)
    elif isinstance(value, dict):
        for key, item in value.items():
            yield key
            yield from _strings(item)


def response_leaks(canary: str, response: ModelResponse) -> bool:
    """Check serialized calls as well as decoded strings containing escaped whitespace."""
    texts = [response.content, response.model_dump_json(include={"tool_calls"})]
    texts.extend(text for call in response.tool_calls for text in _strings(call.arguments.root))
    return any(is_leak(canary, text) for text in texts)
