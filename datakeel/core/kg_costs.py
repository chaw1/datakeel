# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Preserve known stage costs when another stage has an unknown provider tariff."""

from collections.abc import Sequence
from decimal import Decimal

from datakeel.core.harness_models import ModelCallTrace


def known_cost(traces: Sequence[ModelCallTrace], stage: str | None = None) -> Decimal | None:
    """Sum observed costs for the selected stage, returning unknown only within that stage."""
    selected = [trace for trace in traces if stage is None or trace.call_type == stage]
    if any(trace.billing_status == "unknown" for trace in selected):
        return None
    return sum((trace.cost_usd for trace in selected), start=Decimal(0))
