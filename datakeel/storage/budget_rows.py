# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Internal durable reservations and account balances for model budgets."""

from typing import Any

from sqlalchemy import JSON, BigInteger, Float, String
from sqlalchemy.orm import Mapped, mapped_column

from datakeel.core.models import new_id, utcnow
from datakeel.storage.base import Base


class BudgetAccountRow(Base):
    """Serialize spent plus reserved consumption for one conversation or UTC day."""

    __tablename__ = "budget_accounts"
    key: Mapped[str] = mapped_column(String, primary_key=True)
    token_limit: Mapped[int] = mapped_column(BigInteger)
    usd_limit_nanos: Mapped[int] = mapped_column(BigInteger)
    used_tokens: Mapped[int] = mapped_column(BigInteger, default=0)
    reserved_tokens: Mapped[int] = mapped_column(BigInteger, default=0)
    spent_nanos: Mapped[int] = mapped_column(BigInteger, default=0)
    reserved_nanos: Mapped[int] = mapped_column(BigInteger, default=0)


class BudgetReservationRow(Base):
    """Preserve each call's upper bound and price snapshot across restarts."""

    __tablename__ = "budget_reservations"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    conversation_id: Mapped[str] = mapped_column(String, index=True)
    model: Mapped[str] = mapped_column(String)
    day: Mapped[str] = mapped_column(String, index=True)
    tokens: Mapped[int] = mapped_column(BigInteger)
    cost_nanos: Mapped[int] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(String, default="RESERVED")
    price: Mapped[dict[str, Any]] = mapped_column(JSON)
    price_version: Mapped[str] = mapped_column(String)
    reason: Mapped[str] = mapped_column(String, default="")
    created_at: Mapped[float] = mapped_column(Float, default=lambda: utcnow().timestamp())
