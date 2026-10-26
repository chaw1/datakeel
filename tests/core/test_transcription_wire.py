# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Keep vendor response metadata outside the consumed visual transcription boundary."""

import pytest
from pydantic import ValidationError

from datakeel.core.transcription_wire import TranscriptionResponse


def test_response_when_vendor_metadata_present_preserves_consumed_fields() -> None:
    """Unrelated fields at every provider envelope level do not discard valid output."""
    response = TranscriptionResponse.model_validate_json(
        '{"choices":[{"message":{"content":"Alpha","vendor":"ignored"},'
        '"finish_reason":"stop","vendor":"ignored"}],'
        '"usage":{"prompt_tokens":12,"completion_tokens":3,"vendor":"ignored"},'
        '"vendor":"ignored"}'
    )
    assert response.choices[0].message.content == "Alpha"
    assert response.choices[0].finish_reason == "stop"
    assert (response.usage.prompt_tokens, response.usage.completion_tokens) == (12, 3)
    assert "vendor" not in response.model_dump_json()


def test_response_when_ollama_usage_present_keeps_native_fields() -> None:
    """The shared model retains native finish and accounting fields without conversion."""
    response = TranscriptionResponse.model_validate_json(
        '{"message":{"content":"Alpha"},"done_reason":"length",'
        '"prompt_eval_count":12,"eval_count":3}'
    )
    assert response.message.content == "Alpha"
    assert response.done_reason == "length"
    assert (response.prompt_eval_count, response.eval_count) == (12, 3)


@pytest.mark.parametrize(
    "payload",
    [
        '{"usage":{"prompt_tokens":-1}}',
        '{"usage":{"completion_tokens":-1}}',
        '{"prompt_eval_count":-1}',
        '{"eval_count":-1}',
    ],
)
def test_response_when_usage_negative_rejects(payload: str) -> None:
    """Malformed accounting cannot escape the frozen provider response boundary."""
    with pytest.raises(ValidationError):
        TranscriptionResponse.model_validate_json(payload)
