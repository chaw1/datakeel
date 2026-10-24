# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Real extraction metering distinguishes observed usage, known prices and unknown charges."""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

import pytest

from datakeel.core.errors import BudgetError
from datakeel.core.harness_pricing import nanos_to_usd, usage_cost
from datakeel.core.kg_errors import KGExtractionError
from datakeel.core.kg_models import TextBlock
from datakeel.kg.extractors import FakeExtractor
from datakeel.kg.loader import get_profile, get_schema
from datakeel.storage.harness_service import list_traces
from datakeel.storage.kg_pricing import metering_config
from datakeel.worker.kg_metering import MeteredExtractor
from tests.kg.integration_helpers import pair_result

if TYPE_CHECKING:
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
    """Unknown tariffs settle conservative reservations while retaining observed token counts."""
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
    assert trace.observed_usage is not None
    assert trace.observed_usage.input_tokens == (12 if usage else 0)
    assert trace.cost_usd > Decimal(0)
    assert trace.accounted_tokens > 21


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
