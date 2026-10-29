# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Consistent coverage descriptions for stored rule and dataset reports."""

from datakeel.core.dq_models import DqResult


def coverage_text(result: DqResult | None) -> str:
    """Distinguish complete observations from legacy results or unsuccessful executions."""
    if result is None or result.coverage != "complete" or result.rows_total is None:
        return "coverage unknown"
    return f"coverage 100% ({result.rows_scanned}/{result.rows_total} rows; complete)"
