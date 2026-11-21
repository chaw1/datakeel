# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Fallback attempts clear an old preview before releasing independently checked text."""

from __future__ import annotations

from typing import TYPE_CHECKING

from datakeel.agent.service import create_conversation, send_message
from datakeel.core.agent_models import MessageInput, ModelRequest, ModelResponse
from datakeel.core.canary import is_leak
from datakeel.core.errors import ProviderError
from datakeel.core.harness_models import TokenUsage
from datakeel.storage.conversation_secrets import get_canary
from tests.routing.protocol_helpers import configure_fallback
from tests.runtime.test_realtime_streaming import StreamingProvider

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    import pytest

    from datakeel.storage.database import Database


def test_retry_resets_visible_prefix_before_another_attempt_can_complete_a_fragment(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two individually safe attempts cannot concatenate into a visible 16-character secret."""
    config, _settings, _backup = configure_fallback(tmp_path, monkeypatch, "openai")
    root = create_conversation(db, config)
    canary = get_canary(db, root.id)
    first_half, second_half = canary[4:12], canary[12:20]
    attempts: list[str] = []

    def invoke(request: ModelRequest, emit: Callable[[str], None] | None) -> ModelResponse:
        assert emit is not None
        attempts.append(request.model)
        if len(attempts) == 1:
            emit(first_half + "x" * 28)
            reason = "timeout"
            raise ProviderError(reason)
        emit(second_half)
        return ModelResponse(content=second_half, usage=TokenUsage(input_tokens=3, output_tokens=2))

    events = list(
        send_message(
            db, root.id, MessageInput(content="Explain"), provider=StreamingProvider(invoke)
        )
    )
    deltas = [event.text for event in events if event.event == "text_delta"]
    assert deltas == [first_half, "", second_half]
    preview = ""
    for delta in deltas:
        preview = preview + delta if delta else ""
        assert not is_leak(canary, preview)
    assert len(attempts) == 2
    assert next(event.text for event in events if event.event == "text") == second_half
