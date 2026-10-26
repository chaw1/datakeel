# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Keep visual estimates tied to the complete versioned prompt rather than a magic allowance."""

from math import ceil

import pytest

from datakeel.core.context_tokens import estimate_tokens
from datakeel.core.transcription_models import CoordinateSpace
from datakeel.transcription.prompt import (
    COORDINATE_PROMPT,
    TRANSCRIBE_PROMPT,
    input_token_bound,
    transcription_prompt,
)


def test_input_token_bound_when_dimensions_change_includes_image_and_prompt() -> None:
    """Consent and worker reservation can share exactly the same prompt-aware upper bound."""
    assert input_token_bound(120, 80) == ceil(120 * 80 / 1024 + 2) + estimate_tokens(
        TRANSCRIBE_PROMPT
    )
    assert input_token_bound(120, 800) > input_token_bound(120, 80)


@pytest.mark.parametrize(("space", "maximum"), [("normalized_1000", "1000"), ("normalized_1", "1")])
def test_prompt_when_normalized_declares_axes_and_preserves_corrected_size(
    space: CoordinateSpace, maximum: str
) -> None:
    """A normalized provider receives explicit limits without pretending they are pixels."""
    prompt = transcription_prompt("image-transcription-v2", 1800, 880, space)
    assert f"x 和 y 均在 0 到 {maximum} 之间" in prompt
    assert f"原图右下角为 [{maximum},{maximum}]" in prompt
    assert "Corrected image size: 1800 x 880 pixels." in prompt
    assert "原图像素坐标" not in prompt


def test_prompt_when_legacy_or_pixel_retains_original_instruction() -> None:
    """Default pixel output and legacy v1 preserve the original prompt bytes."""
    assert transcription_prompt("image-transcription-v2") == COORDINATE_PROMPT
    assert transcription_prompt("image-transcription-v2", coordinate_space="pixel") == (
        COORDINATE_PROMPT
    )
    assert transcription_prompt("image-transcription-v1", 120, 80, "normalized_1") == (
        TRANSCRIBE_PROMPT
    )


@pytest.mark.parametrize("space", ["pixel", "normalized_1000", "normalized_1"])
def test_input_token_bound_when_coordinate_space_changes_binds_complete_prompt(
    space: CoordinateSpace,
) -> None:
    """Approval and metering reserve every byte of the selected coordinate declaration."""
    assert input_token_bound(1800, 880, "image-transcription-v2", space) == ceil(
        1800 * 880 / 1024 + 2
    ) + estimate_tokens(transcription_prompt("image-transcription-v2", 1800, 880, space))
