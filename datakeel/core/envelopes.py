# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Compact data-only envelopes at the prompt boundary, never in stored transcripts."""

import json
from typing import TYPE_CHECKING, cast

from datakeel.core.agent_models import ChatMessage

if TYPE_CHECKING:
    from pydantic import JsonValue

MARKER = "data-only"
ENVELOPE_SIZE = 3


def envelope(message: ChatMessage) -> ChatMessage:
    """Encode tool provenance and its exact JSON value as untrusted data."""
    if message.role != "tool":
        return message
    try:
        value = cast("JsonValue", json.loads(message.content))
    except json.JSONDecodeError:
        value = message.content
    content = json.dumps([MARKER, message.name, value], ensure_ascii=False, separators=(",", ":"))
    return message.model_copy(update={"content": content})


def unwrap(message: ChatMessage) -> ChatMessage:
    """Let the deterministic demo interpret prompt data without removing its accounting."""
    if message.role != "tool":
        return message
    value = cast("JsonValue", json.loads(message.content))
    if (
        isinstance(value, list)
        and len(value) == ENVELOPE_SIZE
        and value[:2] == [MARKER, message.name]
    ):
        content = value[2] if isinstance(value[2], str) else json.dumps(value[2])
        return message.model_copy(update={"content": content})
    return message
