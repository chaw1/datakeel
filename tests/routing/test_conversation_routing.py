# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Auto only routes to models the configured endpoint serves; otherwise it says why."""

from __future__ import annotations

from typing import TYPE_CHECKING

import yaml

from datakeel.agent.service import conversation_defaults
from datakeel.core.agent_models import ConversationCreate
from datakeel.core.routing_models import TierState
from datakeel.routing.config import load_config, validate_config
from datakeel.routing.tiers import select_model

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

KEYS = ("DATAKEEL_OPENAI_API_KEY", "DATAKEEL_ANTHROPIC_API_KEY", "DATAKEEL_MODEL_ROUTING_FILE")
ENDPOINTS = ("DATAKEEL_OPENAI_BASE_URL", "DATAKEEL_OPENAI_URL")


def _clean(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (*KEYS, *ENDPOINTS):
        monkeypatch.delenv(name, raising=False)


def test_only_deepseek_configured_routes_every_tier_to_deepseek(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A DeepSeek base URL never sends gpt model names: all three tiers use DeepSeek."""
    _clean(monkeypatch)
    monkeypatch.setenv("DATAKEEL_OPENAI_API_KEY", "test-only")
    monkeypatch.setenv("DATAKEEL_OPENAI_BASE_URL", "https://api.deepseek.com")
    defaults = conversation_defaults()
    assert (defaults.provider, defaults.model, defaults.problem) == ("openai", "auto", None)
    tiers = load_config().providers["openai"].tiers
    assert {tiers.simple, tiers.multi_step, tiers.high_risk} == {"deepseek-flash"}
    session = ConversationCreate(provider="openai", model="auto")
    for state in (TierState(), TierState(response_has_plan=True)):
        assert select_model(session, state, load_config()).model == "deepseek-flash"


def test_without_a_usable_model_the_page_is_told_it_is_a_configuration_problem(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No key, or an endpoint with no known tiers, falls back to the demo with a reason."""
    _clean(monkeypatch)
    missing = conversation_defaults()
    assert (missing.provider, missing.problem) == ("fake", "no_model_key")
    monkeypatch.setenv("DATAKEEL_OPENAI_API_KEY", "test-only")
    monkeypatch.setenv("DATAKEEL_OPENAI_BASE_URL", "https://llm.example.com/v1")
    unknown = conversation_defaults()
    assert (unknown.provider, unknown.problem, unknown.endpoint) == (
        "fake",
        "unrouted_endpoint",
        "llm.example.com",
    )
    monkeypatch.delenv("DATAKEEL_OPENAI_BASE_URL")
    openai = conversation_defaults()
    assert (openai.provider, openai.problem) == ("openai", None)
    assert load_config().providers["openai"].tiers.simple == "gpt-4.1-mini"


def test_endpoint_tiers_need_priced_models_of_that_provider(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An endpoint naming a model without a price is a located configuration error."""
    _clean(monkeypatch)
    source = load_config()
    document = source.model_dump(mode="json")
    document["endpoints"]["api.deepseek.com"]["tiers"]["high_risk"] = "unpriced-model"
    path = tmp_path / "models.yaml"
    path.write_text(yaml.safe_dump(document))
    errors = validate_config(path)
    assert any("endpoints.api.deepseek.com.models.unpriced-model" in error for error in errors)
