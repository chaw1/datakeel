# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Budget reservations remain atomic, bounded, durable, and exactly settled."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError as ModelValidationError
from sqlalchemy import select

from datakeel.core.errors import BudgetError, ConflictError, NotFoundError, ValidationError
from datakeel.core.harness_models import (
    BudgetLimits,
    BudgetRequest,
    TokenSegment,
    TokenUsage,
    TraceInput,
)
from datakeel.core.models import utcnow
from datakeel.harness.pricing import get_price, load_prices
from datakeel.harness.service import (
    list_accounts,
    list_traces,
    refund,
    reserve,
    settle,
    summarize_costs,
)
from datakeel.storage.budget_rows import BudgetReservationRow
from datakeel.storage.database import Database


def request(conversation: str = "fixture", **limits: int | Decimal) -> BudgetRequest:
    """Build a small conservative reservation using the deterministic tariff."""
    return BudgetRequest(
        conversation_id=conversation,
        model="fake-script",
        input_tokens=100,
        max_output_tokens=20,
        limits=BudgetLimits.model_validate(limits),
    )


def trace(conversation: str = "fixture", turn: int = 1) -> TraceInput:
    """Describe a measured cached call with exact input segment attribution."""
    return TraceInput(
        conversation_id=conversation,
        turn=turn,
        model="fake-script",
        provider="fake",
        segments=[
            TokenSegment(name="system", tokens=60, stable=True),
            TokenSegment(name="user", tokens=40),
        ],
        usage=TokenUsage(
            input_tokens=100, output_tokens=10, cache_read_tokens=40, cache_write_tokens=20
        ),
        latency_ms=12.5,
        stop_reason="stop",
        tool_calls=1,
    )


def test_settle_records_exact_cost_and_refunds_unused_upper_bound(db: Database) -> None:
    """Charge cache subsets once and atomically replace the reservation with usage."""
    held = reserve(db, request())
    assert held.tokens == 120
    assert held.cost_usd == Decimal("0.000165")
    result = settle(db, held.id, trace())
    assert result.cost_usd == Decimal("0.000089")
    assert result.price_version == "2026-10-22"
    assert list_traces(db, "fixture") == [result]
    assert list_traces(db, "absent") == []
    for account in list_accounts(db):
        assert account.used_tokens == 110
        assert account.reserved_tokens == 0
        assert account.reserved_usd == 0
        assert account.spent_usd == result.cost_usd
    assert settle(db, held.id, trace()) == result
    with pytest.raises(ConflictError, match="different trace"):
        settle(db, held.id, trace(turn=2))


@pytest.mark.parametrize(
    "limits",
    [
        {"conversation_tokens": 119},
        {"daily_tokens": 119},
        {"conversation_usd": Decimal("0.000164")},
        {"daily_usd": Decimal("0.000164")},
    ],
)
def test_rejection_is_persistent_and_consumes_no_budget(
    db: Database, limits: dict[str, int | Decimal]
) -> None:
    """Both resource kinds and both scopes reject before the provider can run."""
    with pytest.raises(BudgetError, match="budget exceeded"):
        reserve(db, request(**limits))
    assert all(account.reserved_tokens == 0 for account in list_accounts(db))
    with db.session() as session:
        rejected = session.scalar(select(BudgetReservationRow))
        assert rejected is not None
        assert rejected.status == "REJECTED"


def test_concurrent_reservations_cannot_overbook_daily_budget(db: Database) -> None:
    """Only one concurrent caller can consume the shared day's final allowance."""

    def attempt(index: int) -> str:
        try:
            return reserve(db, request(str(index), daily_tokens=120)).status
        except BudgetError:
            return "REJECTED"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, range(2)))
    assert sorted(results) == ["REJECTED", "RESERVED"]
    day = next(account for account in list_accounts(db) if account.key.startswith("day:"))
    assert day.reserved_tokens == 120


def test_restart_preserves_reservations_and_limits_cannot_be_raised(tmp_path: Path) -> None:
    """A new process connection cannot evade a previously configured ceiling."""
    url = f"sqlite:///{tmp_path / 'restart.db'}"
    first = Database(url)
    first.migrate()
    held = reserve(first, request(conversation_tokens=120))
    first.engine.dispose()
    second = Database(url)
    try:
        with pytest.raises(BudgetError):
            reserve(second, request(conversation_tokens=1000))
        refund(second, held.id, "Provider not called")
        refund(second, held.id, "Idempotent retry")
        assert all(account.reserved_tokens == 0 for account in list_accounts(second))
    finally:
        second.engine.dispose()


def test_refund_and_settle_enforce_reservation_identity(db: Database) -> None:
    """Missing, refunded, settled, and mismatched handles cannot be reused."""
    with pytest.raises(NotFoundError):
        refund(db, "missing", "No call")
    with pytest.raises(NotFoundError):
        settle(db, "missing", trace())
    held = reserve(db, request())
    with pytest.raises(ConflictError, match="does not match"):
        settle(db, held.id, trace("another"))
    refund(db, held.id, "No provider call")
    with pytest.raises(ConflictError, match="not outstanding"):
        settle(db, held.id, trace())
    other = reserve(db, request())
    settle(db, other.id, trace())
    with pytest.raises(ConflictError, match="outstanding"):
        refund(db, other.id, "Already billed")


def test_midnight_settlement_releases_the_original_day(
    db: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A provider call spanning midnight cannot strand the old day's hold."""
    yesterday = utcnow() - timedelta(days=1)
    monkeypatch.setattr("datakeel.storage.budget_service.utcnow", lambda: yesterday)
    held = reserve(db, request())
    settle(db, held.id, trace())
    day = next(account for account in list_accounts(db) if account.key.startswith("day:"))
    assert day.key == f"day:{yesterday.date().isoformat()}"
    assert day.reserved_tokens == 0
    assert day.used_tokens == 110


def test_cost_summaries_support_every_grouping(db: Database) -> None:
    """Summaries use complete persisted usage with exact decimal addition."""
    for conversation in ("first", "second"):
        held = reserve(db, request(conversation))
        settle(db, held.id, trace(conversation))
    assert [row.key for row in summarize_costs(db)] == ["first", "second"]
    for grouping in ("day", "model"):
        summary = summarize_costs(db, grouping)
        assert len(summary) == 1
        assert summary[0].calls == 2
        assert summary[0].input_tokens == 200
        assert summary[0].output_tokens == 20
        assert summary[0].cache_read_tokens == 80
        assert summary[0].cache_write_tokens == 40
        assert summary[0].cost_usd == Decimal("0.000178")


def test_invalid_token_attribution_is_rejected_before_settlement() -> None:
    """Billing counts and segment attribution cannot silently disagree."""
    with pytest.raises(ModelValidationError, match="subset"):
        TokenUsage(input_tokens=1, cache_read_tokens=2)
    with pytest.raises(ModelValidationError, match="sum"):
        TraceInput.model_validate({**trace().model_dump(), "segments": []})


def test_official_prices_and_unknown_models_are_explicit() -> None:
    """Price snapshots retain provenance and refuse unpriced calls."""
    table = load_prices()
    assert table.currency == "USD"
    assert get_price("gpt-4.1-mini")[1].input == Decimal("0.4")
    assert get_price("claude-haiku-4-5-20251001")[1].cache_write == Decimal("1.25")
    with pytest.raises(ValidationError, match="No price"):
        get_price("unpriced")


@pytest.mark.parametrize(
    "limits",
    [
        {"conversation_tokens": 120},
        {"daily_tokens": 120},
        {"conversation_usd": Decimal("0.000165")},
        {"daily_usd": Decimal("0.000165")},
    ],
)
def test_settle_when_actual_usage_exceeds_limit_persists_charge_and_reports_stop(
    db: Database, limits: dict[str, int | Decimal]
) -> None:
    """A provider overrun remains billed and blocks tool dispatch after settlement."""
    held = reserve(db, request(**limits))
    actual = trace().model_copy(update={"usage": TokenUsage(input_tokens=100, output_tokens=101)})
    result = settle(db, held.id, actual)
    assert result.budget_exceeded
    assert result.billing_status == "actual"
    assert result.accounted_tokens == 201
    assert result.cost_usd == Decimal("0.000302")
    assert list_traces(db) == [result]
    assert settle(db, held.id, actual) == result
    assert all(account.used_tokens == 201 for account in list_accounts(db))
    with pytest.raises(BudgetError):
        reserve(db, request(**limits))


@pytest.mark.parametrize(
    "limits",
    [
        {"conversation_tokens": 240},
        {"daily_tokens": 240},
        {"conversation_usd": Decimal("0.000330")},
        {"daily_usd": Decimal("0.000330")},
    ],
)
def test_unknown_billing_when_retried_consumes_persistent_conservative_budget(
    db: Database, limits: dict[str, int | Decimal]
) -> None:
    """Ambiguous provider failures cannot turn repeated calls into free budget retries."""
    unknown = TraceInput.model_validate(
        {
            **trace().model_dump(),
            "segments": [],
            "usage": TokenUsage(),
            "billing_status": "unknown",
            "stop_reason": "provider_error",
            "tool_calls": 0,
        }
    )
    for _ in range(2):
        held = reserve(db, request(**limits))
        result = settle(db, held.id, unknown)
        assert result.cost_usd == held.cost_usd
        assert result.accounted_tokens == held.tokens
        assert result.usage == TokenUsage()
        assert result.billing_status == "unknown"
        assert not result.budget_exceeded
        assert settle(db, held.id, unknown) == result
    with pytest.raises(BudgetError):
        reserve(db, request(**limits))
    for account in list_accounts(db):
        assert account.used_tokens == 240
        assert account.spent_usd == Decimal("0.000330")
        assert account.reserved_tokens == account.reserved_usd == 0
    for grouping in ("conversation", "day", "model"):
        summary = summarize_costs(db, grouping)[0]
        assert summary.unknown_calls == summary.calls == 2
        assert summary.unknown_cost_usd == summary.cost_usd == Decimal("0.000330")
        assert summary.input_tokens == summary.output_tokens == 0


def test_unknown_billing_when_usage_is_supplied_rejects_invented_observations() -> None:
    """Unknown usage stays unknown while a separate accounting field carries the estimate."""
    with pytest.raises(ModelValidationError, match="cannot claim observed"):
        TraceInput.model_validate({**trace().model_dump(), "billing_status": "unknown"})


def test_settle_when_usage_and_other_reservations_exceed_day_reports_overrun(db: Database) -> None:
    """A concurrent call's outstanding hold counts toward post-settlement safety."""
    first = reserve(db, request("first", daily_tokens=240))
    second = reserve(db, request("second", daily_tokens=240))
    actual = trace("first").model_copy(
        update={"usage": TokenUsage(input_tokens=100, output_tokens=101)}
    )
    result = settle(db, first.id, actual)
    assert result.budget_exceeded
    day = next(account for account in list_accounts(db) if account.key.startswith("day:"))
    assert day.used_tokens == 201
    assert day.reserved_tokens == second.tokens == 120
