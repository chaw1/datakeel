# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Sentinel entropy, partial detection and output-budget boundaries."""

import re

import pytest

from datakeel.core.agent_models import ModelResponse, ToolCall
from datakeel.core.canary import canary_instruction, generate_canary, is_leak, response_leaks
from datakeel.core.context_tokens import estimate_tokens
from datakeel.core.models import JsonDocument

CANARY = "dkc_0123456789abcdef01234567"


def test_generation_is_unique_and_context_overhead_is_bounded() -> None:
    """Use at least 24 random hexadecimal characters within the 96-byte segment cap."""
    values = {generate_canary() for _ in range(100)}
    assert len(values) == 100
    assert all(re.fullmatch(r"dkc_[0-9a-f]{24,}", value) for value in values)
    assert all(estimate_tokens(canary_instruction(value)) + 16 <= 96 for value in values)


@pytest.mark.parametrize(
    "text", [CANARY, CANARY.upper(), " \n\t".join(CANARY), CANARY[4:20], CANARY[-16:]]
)
def test_full_and_random_fragments_are_leaks(text: str) -> None:
    """Case folding and whitespace cannot conceal full or 16-character random fragments."""
    assert is_leak(CANARY, text)


@pytest.mark.parametrize("text", ["dkc_", "DKC_", CANARY[4:19], "ordinary output"])
def test_prefix_and_short_fragments_are_not_leaks(text: str) -> None:
    """A prefix alone or fewer than sixteen random characters is insufficient."""
    assert not is_leak(CANARY, text)


def test_serialized_tool_parameters_include_nested_and_escaped_strings() -> None:
    """Inspect nested values and keys even when JSON escapes actual whitespace."""
    response = ModelResponse(
        tool_calls=[
            ToolCall(
                name="search_files",
                arguments=JsonDocument({"nested": [None, 1, {"note": "\n".join(CANARY)}]}),
            )
        ]
    )
    assert response_leaks(CANARY, response)
    assert not is_leak("", "ordinary output")
