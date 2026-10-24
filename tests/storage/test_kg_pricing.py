# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Bundled extraction tariffs expose a frozen approval ceiling without contacting a provider."""

from __future__ import annotations

from typing import TYPE_CHECKING

from datakeel.core.harness_pricing import nanos_to_usd, reservation_cost
from tests.kg.integration_helpers import prepare_graph, text_dataset

if TYPE_CHECKING:
    from pathlib import Path

    from datakeel.storage.database import Database


def test_cloud_approval_freezes_known_peak_tariff_and_upper_cost(
    db: Database, tmp_path: Path
) -> None:
    """The default cloud choice is priced while recorded model identities remain untouched."""
    dataset = text_dataset(db, tmp_path, ("Acme uses Widget.",))
    plan = prepare_graph(db, dataset, "cloud")
    estimate = plan.impact.kg_estimate
    assert estimate is not None
    assert estimate.model == "deepseek-flash"
    assert estimate.price is not None
    assert estimate.cost_upper_usd is not None
    assert "2026-10-24" in estimate.price.source
    assert estimate.cost_upper_usd == nanos_to_usd(
        reservation_cost(
            estimate.price, estimate.input_tokens, estimate.blocks * estimate.max_output_tokens
        )
    )
    assert estimate.cost_upper_usd > 0
