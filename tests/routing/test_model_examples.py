# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""The model-routing template is strict and becomes usable only with declared tariffs."""

from pathlib import Path

import pytest

from datakeel.core.agent_models import ConversationCreate
from datakeel.core.routing_models import TierState
from datakeel.routing.config import load_config, load_prices, validate_config
from datakeel.routing.tiers import model_chain, select_model

EXAMPLE = Path("examples/model-routing.yaml")
EXAMPLE_MODELS = ("reader-primary", "planner-primary", "controller-primary", "shared-backup")


def test_model_template_when_prices_unfilled_refuses_startup() -> None:
    """Comments never accidentally turn unknown tariffs into zero-cost model calls."""
    errors = validate_config(EXAMPLE)
    assert len(errors) == len(EXAMPLE_MODELS)
    assert all("model has no price" in error for error in errors)


@pytest.mark.parametrize(
    ("state", "primary"),
    [
        (TierState(), "reader-primary"),
        (TierState(response_has_tool_result=True), "planner-primary"),
        (TierState(response_has_plan=True), "controller-primary"),
    ],
)
def test_model_template_when_offline_tariffs_supplied_selects_tiers_and_backup(
    monkeypatch: pytest.MonkeyPatch, state: TierState, primary: str
) -> None:
    """Synthetic prices validate the published example without any provider access."""
    prices = load_prices()
    template = next(price for price in prices.models if price.model == "gpt-4.1-mini")
    prices = prices.model_copy(
        update={
            "models": [
                *prices.models,
                *[template.model_copy(update={"model": name}) for name in EXAMPLE_MODELS],
            ]
        }
    )
    monkeypatch.setattr("datakeel.routing.config.load_prices", lambda: prices)
    config = load_config(EXAMPLE)
    session = ConversationCreate(provider="openai", model="auto")
    selected = select_model(session, state, config)
    assert selected.model == primary
    assert not selected.pinned
    assert model_chain(session, selected, config) == [primary, "shared-backup"]
