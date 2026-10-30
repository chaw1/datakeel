# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Price prelabel calls from image counts, sizes, token prices and expected output tokens."""

import math
from decimal import Decimal

from datakeel.core.prelabel_models import CloudModelConfig, PrelabelEstimate
from datakeel.prelabel.images import image_tokens, sent_size

_THOUSAND = Decimal(1000)
_BYTES_PER_TOKEN = 3.3
_TEMPLATE_TOKENS = 25


def token_cost(config: CloudModelConfig, input_tokens: int, output_tokens: int) -> Decimal:
    """Price measured or estimated tokens at the configured per-thousand rates."""
    return (
        Decimal(str(config.input_price)) * input_tokens
        + Decimal(str(config.output_price)) * output_tokens
    ) / _THOUSAND


def prompt_token_estimate(prompt: str) -> int:
    """Estimate instruction tokens from UTF-8 length plus the chat template's fixed overhead.

    Calibrated on qwen3.5 replies (80 COCO labels: 1438 bytes measured 460 tokens).
    """
    return math.ceil(len(prompt.encode()) / _BYTES_PER_TOKEN) + _TEMPLATE_TOKENS


def call_input_tokens(
    config: CloudModelConfig,
    width: int | None,
    height: int | None,
    prompt_tokens: int | None = None,
) -> int:
    """Instruction tokens plus image tiles of the downscaled view; unknown sizes assume worst."""
    side = config.max_image_side
    view = sent_size(width, height, side) if width and height else (side, side)
    instruction = config.prompt_tokens if prompt_tokens is None else prompt_tokens
    return instruction + image_tokens(view[0], view[1], config.token_patch)


def image_estimate(
    config: CloudModelConfig,
    unit_price: float,
    size: tuple[int | None, int | None],
    output_tokens: int | None = None,
    prompt_tokens: int | None = None,
) -> Decimal:
    """Price every view of one image plus the model's per-image charge."""
    calls = 2 if config.cross_check else 1
    tokens = config.expected_output_tokens if output_tokens is None else output_tokens
    per_call = token_cost(config, call_input_tokens(config, *size, prompt_tokens), tokens)
    return per_call * calls + Decimal(str(unit_price))


def run_estimate(  # noqa: PLR0913  # Prices, sizes and both token calibrations are independent.
    config: CloudModelConfig,
    unit_price: float,
    currency: str,
    sizes: list[tuple[int | None, int | None]],
    already_done: int = 0,
    *,
    prompt_tokens: int | None = None,
    output_tokens: int | None = None,
    observed_calls: int = 0,
) -> PrelabelEstimate:
    """Freeze the expected total and an upper bound at the maximum output length."""
    total = sum(
        (image_estimate(config, unit_price, size, output_tokens, prompt_tokens) for size in sizes),
        Decimal(0),
    )
    upper = sum(
        (
            image_estimate(config, unit_price, size, config.max_output_tokens, prompt_tokens)
            for size in sizes
        ),
        Decimal(0),
    )
    calls = 2 if config.cross_check else 1
    count = len(sizes)
    input_tokens = sum(call_input_tokens(config, *size, prompt_tokens) for size in sizes) * calls
    expected = config.expected_output_tokens if output_tokens is None else output_tokens
    return PrelabelEstimate(
        images=count,
        already_done=already_done,
        calls_per_image=calls,
        input_tokens_per_image=round(input_tokens / count) if count else 0,
        output_tokens_per_image=expected * calls,
        per_image=float(total / count) if count else 0.0,
        total=float(total),
        upper_bound=float(upper),
        currency=currency,
        observed_calls=observed_calls,
    )
