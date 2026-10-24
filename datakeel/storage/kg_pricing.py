# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Freeze local tariff evidence and explicitly unknown accounting envelopes."""

from decimal import Decimal

from datakeel.core.harness_pricing import ModelPrice, PriceTable
from datakeel.core.kg_contracts import ExtractionProfile
from datakeel.core.kg_execution import KGMeteringConfig
from datakeel.kg.loader import contracts_path, load_contract


def metering_config(profile: ExtractionProfile, run_id: str) -> KGMeteringConfig:
    """Use zero offline cost or the checked snapshot, never invent a known model price."""
    if profile.extractor != "llm":
        price = ModelPrice(
            model=profile.model,
            provider=profile.provider,
            input=Decimal(0),
            output=Decimal(0),
            cache_read=Decimal(0),
            cache_write=Decimal(0),
            source="Offline execution has no provider charge",
        )
        return KGMeteringConfig(
            run_id=run_id, profile=profile, price=price, price_version="offline", known_price=True
        )
    table = load_contract(contracts_path().parent / "model-prices.yaml", PriceTable)
    price = next((item for item in table.models if item.model == profile.model), None)
    version = table.version_date.isoformat()
    if price is not None:
        return KGMeteringConfig(
            run_id=run_id, profile=profile, price=price, price_version=version, known_price=True
        )
    envelope = ModelPrice(
        model=profile.model,
        provider=profile.provider,
        input=max(item.input for item in table.models),
        output=max(item.output for item in table.models),
        cache_read=max(item.cache_read for item in table.models),
        cache_write=max(item.cache_write for item in table.models),
        source="Unknown-price budget envelope; not a quoted provider tariff",
    )
    return KGMeteringConfig(
        run_id=run_id,
        profile=profile,
        price=envelope,
        price_version=f"unknown:{version}",
        known_price=False,
    )
