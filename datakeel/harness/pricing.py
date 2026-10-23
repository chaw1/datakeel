# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Load a versioned official price snapshot without provider requests."""

from pathlib import Path

import yaml

from datakeel.core.errors import ValidationError
from datakeel.core.harness_pricing import ModelPrice, PriceTable
from datakeel.harness.resources import contract_path

PRICE_PATH = contract_path("model-prices.yaml")


def load_prices(path: Path = PRICE_PATH) -> PriceTable:
    """Read and validate the checked-in table without making provider requests."""
    return PriceTable.model_validate(yaml.safe_load(path.read_text()))


def get_price(model: str) -> tuple[str, ModelPrice]:
    """Return one explicit model price, refusing unpriced model calls."""
    table = load_prices()
    for price in table.models:
        if price.model == model:
            return table.version_date.isoformat(), price
    msg = f"No price configured for model: {model}"
    raise ValidationError(msg)
