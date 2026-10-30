# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Price prelabel calls from image counts, sizes, token prices and expected output tokens."""

from decimal import Decimal

from datakeel.core.prelabel_models import CloudModelConfig, PrelabelEstimate
from datakeel.prelabel.images import image_tokens, sent_size

_THOUSAND = Decimal(1000)


def token_cost(config: CloudModelConfig, input_tokens: int, output_tokens: int) -> Decimal:
    """Price measured or estimated tokens at the configured per-thousand rates."""
    return (
        Decimal(str(config.input_price)) * input_tokens
        + Decimal(str(config.output_price)) * output_tokens
    ) / _THOUSAND


def call_input_tokens(config: CloudModelConfig, width: int | None, height: int | None) -> int:
    """Instruction tokens plus image tiles of the downscaled view; unknown sizes assume worst."""
    side = config.max_image_side
    view = sent_size(width, height, side) if width and height else (side, side)
    return config.prompt_tokens + image_tokens(view[0], view[1], config.token_patch)


def image_estimate(
    config: CloudModelConfig,
    unit_price: float,
    size: tuple[int | None, int | None],
    output_tokens: int | None = None,
) -> Decimal:
    """Price every view of one image plus the model's per-image charge."""
    calls = 2 if config.cross_check else 1
    tokens = config.expected_output_tokens if output_tokens is None else output_tokens
    per_call = token_cost(config, call_input_tokens(config, *size), tokens)
    return per_call * calls + Decimal(str(unit_price))


def run_estimate(
    config: CloudModelConfig,
    unit_price: float,
    currency: str,
    sizes: list[tuple[int | None, int | None]],
    already_done: int = 0,
) -> PrelabelEstimate:
    """Freeze the expected total and an upper bound at the maximum output length."""
    total = sum((image_estimate(config, unit_price, size) for size in sizes), Decimal(0))
    upper = sum(
        (image_estimate(config, unit_price, size, config.max_output_tokens) for size in sizes),
        Decimal(0),
    )
    calls = 2 if config.cross_check else 1
    count = len(sizes)
    input_tokens = sum(call_input_tokens(config, *size) for size in sizes) * calls
    return PrelabelEstimate(
        images=count,
        already_done=already_done,
        calls_per_image=calls,
        input_tokens_per_image=round(input_tokens / count) if count else 0,
        output_tokens_per_image=config.expected_output_tokens * calls,
        per_image=float(total / count) if count else 0.0,
        total=float(total),
        upper_bound=float(upper),
        currency=currency,
    )
