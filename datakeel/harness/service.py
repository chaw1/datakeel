# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Typed entry points for persistent metering and conservative budgets."""

from datakeel.core.harness_models import BudgetRequest, BudgetReservation
from datakeel.harness.pricing import get_price
from datakeel.storage.budget_accounts import list_accounts
from datakeel.storage.budget_service import refund
from datakeel.storage.budget_service import reserve as reserve_budget
from datakeel.storage.database import Database
from datakeel.storage.harness_service import list_traces, settle, summarize_costs

__all__ = ["list_accounts", "list_traces", "refund", "reserve", "settle", "summarize_costs"]


def reserve(db: Database, request: BudgetRequest) -> BudgetReservation:
    """Freeze the current tariff and reserve both durable budget scopes."""
    version, price = get_price(request.model)
    return reserve_budget(db, request, version, price)
