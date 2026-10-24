# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Real extraction metering distinguishes observed usage, known prices and unknown charges."""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

import pytest

from datakeel.core.errors import BudgetError
from datakeel.core.harness_models import TokenUsage
from datakeel.core.harness_pricing import nanos_to_usd, usage_cost
from datakeel.core.kg_errors import ExtractionProviderError, KGExtractionError
from datakeel.core.kg_models import TextBlock
from datakeel.kg.extractors import FakeExtractor, checked_extract
from datakeel.kg.loader import get_profile, get_schema
from datakeel.storage.budget_accounts import list_accounts
from datakeel.storage.harness_service import list_traces
from datakeel.storage.kg_pricing import metering_config
from datakeel.worker.kg_metering import MeteredExtractor
from tests.kg.integration_helpers import pair_result

if TYPE_CHECKING:
    from datakeel.core.kg_contracts import KGSchema
    from datakeel.core.kg_models import ExtractionResult
    from datakeel.storage.database import Database


def test_known_price_settles_observed_usage_and_stops_after_overrun(db: Database) -> None:
    """Unexpected provider usage remains traceable and prevents any further model call."""
    profile = get_profile("cloud").model_copy(update={"model": "gpt-4.1-mini"})
    config = metering_config(profile, "known-extraction").model_copy(
        update={"budget_tokens": 10000}
    )
    assert config.known_price
    output = pair_result().model_copy(update={"input_tokens": 12000, "output_tokens": 500})
    adapter = FakeExtractor((output,))
    metered = MeteredExtractor(db, config, adapter)
    block = TextBlock(text="Acme uses Widget.", start=0, end=17)
    metered.extract(block, get_schema())
    trace = list_traces(db, config.run_id)[0]
    assert trace.call_type == "extraction"
    assert trace.billing_status == "actual"
    assert trace.usage.input_tokens == 12000
    assert trace.cost_usd == nanos_to_usd(usage_cost(config.price, trace.usage))
    assert trace.budget_exceeded
    resumed = MeteredExtractor(db, config, adapter)
    with pytest.raises(BudgetError, match="budget exceeded"):
        resumed.extract(block, get_schema())
    assert adapter.calls == 1


@pytest.mark.parametrize("usage", [True, False])
def test_unknown_price_preserves_observations_without_claiming_actual_cost(
    db: Database, *, usage: bool
) -> None:
    """Unknown tariffs keep conservative fees but charge complete observed token counts."""
    profile = get_profile("cloud").model_copy(update={"model": "fixture-unknown"})
    config = metering_config(profile, "unknown-extraction")
    output = pair_result().model_copy(
        update={
            "input_tokens": 12 if usage else None,
            "output_tokens": 9 if usage else None,
        }
    )
    metered = MeteredExtractor(db, config, FakeExtractor((output,)))
    metered.extract(TextBlock(text="Acme uses Widget.", start=0, end=17), get_schema())
    trace = list_traces(db, config.run_id)[0]
    assert not config.known_price
    assert trace.billing_status == "unknown"
    assert trace.usage.input_tokens == trace.usage.output_tokens == 0
    assert trace.cost_usd > Decimal(0)
    if usage:
        assert trace.observed_usage == TokenUsage(input_tokens=12, output_tokens=9)
        assert trace.accounted_tokens == 21
    else:
        assert trace.observed_usage is None
        assert trace.accounted_tokens > 21
    account = next(item for item in list_accounts(db) if item.key.startswith("conversation:"))
    assert account.used_tokens == trace.accounted_tokens


def test_failed_request_is_settled_before_sanitized_error_escapes(db: Database) -> None:
    """A provider failure receives one unknown-charge trace and no silent unreserved retry."""
    profile = get_profile("cloud")
    config = metering_config(profile, "failed-extraction")
    adapter = FakeExtractor(("provider_error",))
    with pytest.raises(KGExtractionError, match="provider_error"):
        MeteredExtractor(db, config, adapter).extract(
            TextBlock(text="Acme uses Widget.", start=0, end=17), get_schema()
        )
    trace = list_traces(db, config.run_id)[0]
    assert trace.billing_status == "unknown"
    assert trace.stop_reason == "provider_error"
    assert trace.call_type == "extraction"
    assert trace.observed_usage is None
    assert adapter.calls == 1


def test_cloud_tariff_uses_peak_prices_and_cached_usage(db: Database) -> None:
    """Charge the current cloud model using the declared conservative tariff and cache subsets."""
    profile = get_profile("cloud")
    config = metering_config(profile, "cloud-extraction")
    assert profile.model == "deepseek-flash"
    assert config.known_price
    assert (config.price.input, config.price.output, config.price.cache_read) == (
        Decimal("0.3"),
        Decimal("1.2"),
        Decimal("0.006"),
    )
    output = pair_result().model_copy(
        update={"input_tokens": 1000, "output_tokens": 100, "cache_read_tokens": 500}
    )
    MeteredExtractor(db, config, FakeExtractor((output,))).extract(
        TextBlock(text="Acme uses Widget.", start=0, end=17), get_schema()
    )
    trace = list_traces(db, config.run_id)[0]
    assert trace.billing_status == "actual"
    assert trace.accounted_tokens == 1100
    assert trace.cost_usd == Decimal("0.000273")


@pytest.mark.parametrize("known_price", [True, False])
@pytest.mark.parametrize("reason", ["parse_error", "truncated"])
def test_unusable_response_preserves_usage_and_charges_actual_tokens(
    db: Database, reason: str, *, known_price: bool
) -> None:
    """A billed parse failure keeps complete usage regardless of whether its tariff is known."""
    profile = get_profile("cloud")
    if not known_price:
        profile = profile.model_copy(update={"model": "fixture-unknown"})
    config = metering_config(profile, "unusable-extraction")
    observed = TokenUsage(input_tokens=80, output_tokens=25)

    class BrokenResponse:
        """Fail only after the injected provider has returned a usage-bearing response."""

        def extract(self, block: TextBlock, schema: KGSchema) -> ExtractionResult:
            """Expose unusable output without concealing its completed model call."""
            if reason == "truncated":
                return pair_result().model_copy(
                    update={"input_tokens": 80, "output_tokens": 25, "finish_reason": "length"}
                )
            raise ExtractionProviderError(reason, observed_usage=observed)

    with pytest.raises(KGExtractionError) as failure:
        checked_extract(
            MeteredExtractor(db, config, BrokenResponse()),
            TextBlock(text="Acme uses Widget.", start=0, end=17),
            get_schema(),
        )
    assert failure.value.observed_usage == observed
    trace = list_traces(db, config.run_id)[0]
    assert trace.observed_usage == (None if known_price else observed)
    assert trace.usage == (observed if known_price else TokenUsage())
    assert trace.accounted_tokens == 105
    assert trace.billing_status == ("actual" if known_price else "unknown")
