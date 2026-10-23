# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Exact price arithmetic shared by metering and its persistence layer."""

from datetime import date
from decimal import ROUND_CEILING, Decimal

from pydantic import Field

from datakeel.core.harness_models import TokenUsage
from datakeel.core.models import BoundaryModel

NANODOLLARS = Decimal(1_000_000_000)
TOKENS_PER_MILLION = Decimal(1_000_000)


class ModelPrice(BoundaryModel):
    """Store USD per million tokens, including the five-minute cache-write tier."""

    model: str
    provider: str
    input: Decimal = Field(ge=0)
    output: Decimal = Field(ge=0)
    cache_read: Decimal = Field(ge=0)
    cache_write: Decimal = Field(ge=0)
    source: str


class PriceTable(BoundaryModel):
    """Identify the checked-in pricing snapshot used for each reservation."""

    version_date: date
    currency: str
    unit: str
    models: list[ModelPrice]


def usd_to_nanos(value: Decimal) -> int:
    """Round a dollar amount upward to the accounting unit."""
    return int((value * NANODOLLARS).to_integral_value(rounding=ROUND_CEILING))


def nanos_to_usd(value: int) -> Decimal:
    """Convert the integer accounting unit to exact decimal dollars."""
    return Decimal(value) / NANODOLLARS


def usage_cost(price: ModelPrice, usage: TokenUsage) -> int:
    """Charge uncached input and both cache categories without double counting."""
    uncached = usage.input_tokens - usage.cache_read_tokens - usage.cache_write_tokens
    amount = (
        uncached * price.input
        + usage.output_tokens * price.output
        + usage.cache_read_tokens * price.cache_read
        + usage.cache_write_tokens * price.cache_write
    ) / TOKENS_PER_MILLION
    return usd_to_nanos(amount)


def reservation_cost(price: ModelPrice, input_tokens: int, output_tokens: int) -> int:
    """Cover the most expensive possible input tier and the output maximum."""
    amount = (
        input_tokens * max(price.input, price.cache_read, price.cache_write)
        + output_tokens * price.output
    ) / TOKENS_PER_MILLION
    return usd_to_nanos(amount)
