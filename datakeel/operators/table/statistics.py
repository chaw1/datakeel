# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Produce bounded distributions without copying suspected personal values."""

from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING

import numpy as np

from datakeel.operators.table.inference import amount_value, numeric_value
from datakeel.operators.table.models import (
    DistributionSummary,
    NumericSummary,
    ValueCount,
)

if TYPE_CHECKING:
    from datakeel.operators.table.models import ColumnType, PiiKind

_NUMERIC_TYPES = {"integer", "number", "amount"}


def _numeric_summary(values: tuple[str, ...], inferred_type: ColumnType) -> NumericSummary | None:
    if inferred_type not in _NUMERIC_TYPES:
        return None
    parser = amount_value if inferred_type == "amount" else numeric_value
    numbers = tuple(number for value in values if (number := parser(value)) is not None)
    if len(numbers) != len(values) or not numbers:
        return None
    # Scaling keeps moments and quantile interpolation finite near float limits.
    scale = max(abs(number) for number in numbers) or 1.0
    normalized = np.array(numbers, dtype=np.float64) / scale
    quantiles = np.quantile(normalized, [0.25, 0.5, 0.75])
    return NumericSummary(
        minimum=min(numbers),
        maximum=max(numbers),
        mean=float(np.mean(normalized)) * scale,
        median=float(quantiles[1]) * scale,
        standard_deviation=float(np.std(normalized)) * scale,
        first_quartile=float(quantiles[0]) * scale,
        third_quartile=float(quantiles[2]) * scale,
    )


def distribution(
    values: tuple[str, ...], inferred_type: ColumnType, pii: tuple[PiiKind, ...], limit: int
) -> DistributionSummary:
    """Summarize values deterministically, withholding all values for PII columns."""
    if not values:
        return DistributionSummary()
    if pii:
        return DistributionSummary(top_values=(ValueCount(value="[REDACTED]", count=len(values)),))
    counts = sorted(Counter(values).items(), key=lambda pair: (-pair[1], pair[0]))[:limit]
    return DistributionSummary(
        numeric=_numeric_summary(values, inferred_type),
        top_values=tuple(ValueCount(value=value, count=count) for value, count in counts),
        minimum_length=min(map(len, values)),
        maximum_length=max(map(len, values)),
    )
