# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Keep visual estimates tied to the complete versioned prompt rather than a magic allowance."""

from math import ceil

from datakeel.core.context_tokens import estimate_tokens
from datakeel.transcription.prompt import TRANSCRIBE_PROMPT, input_token_bound


def test_input_token_bound_when_dimensions_change_includes_image_and_prompt() -> None:
    """Consent and worker reservation can share exactly the same prompt-aware upper bound."""
    assert input_token_bound(120, 80) == ceil(120 * 80 / 1024 + 2) + estimate_tokens(
        TRANSCRIBE_PROMPT
    )
    assert input_token_bound(120, 800) > input_token_bound(120, 80)
