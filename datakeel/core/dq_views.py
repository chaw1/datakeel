# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Immutable public views of monitored table quality."""

from datetime import datetime

from datakeel.core.dq_models import DqResult, DqRule
from datakeel.core.models import BoundaryModel


class DqRuleView(BoundaryModel):
    """Pair a current rule definition with its most recent observation."""

    rule: DqRule
    latest_result: DqResult | None = None
    next_due_at: datetime | None = None


class DqSummary(BoundaryModel):
    """Score only observed rules while keeping non-verdict states explicit."""

    score: float | None = None
    total: int = 0
    passed: int = 0
    failed: int = 0
    errors: int = 0
    baseline_insufficient: int = 0
    pending: int = 0
    open_issues: int = 0
    rules: tuple[DqRuleView, ...] = ()


class DqReport(BoundaryModel):
    """Provide a model-free analysis report grounded in persisted rule observations."""

    summary: DqSummary
    body: str
