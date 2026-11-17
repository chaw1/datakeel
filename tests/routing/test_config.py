# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Configuration errors remain explicit and carry their document location."""

from pathlib import Path

import pytest
import yaml

from datakeel.agent.service import create_conversation
from datakeel.core.agent_models import ConversationCreate
from datakeel.core.errors import ValidationError
from datakeel.core.routing_models import TierState
from datakeel.routing.config import (
    contract_path,
    fallback_chain,
    load_config,
    load_prices,
    price_for,
    validate_config,
)
from datakeel.routing.models import ProviderModels, TierModels
from datakeel.routing.tiers import model_chain, select_model
from datakeel.storage.database import Database


def _write(tmp_path: Path, data: object) -> Path:
    path = tmp_path / "custom-routing.yaml"
    path.write_text(yaml.safe_dump(data))
    return path


def test_default_configuration_when_loaded_uses_only_priced_models() -> None:
    """The shipped default works without custom paths or external price discovery."""
    assert validate_config() == []
    assert price_for("fake-demo")[1].provider == "fake"
    with pytest.raises(ValidationError, match="No price"):
        price_for("missing-model")
    assert str(contract_path("absent-fixture")).endswith("_contracts/absent-fixture")


@pytest.mark.parametrize(
    "replacement",
    [
        {"version": 1, "providers": {}},
        {"version": 1, "providers": {"unknown": {"tiers": {}}}},
        {
            "version": 1,
            "providers": {
                "fake": {
                    "tiers": {"simple": "fake-demo", "high_risk": "fake-demo", "extra": "fake-demo"}
                }
            },
        },
    ],
)
def test_configuration_when_required_or_known_keys_missing_reports_location(
    tmp_path: Path, replacement: dict[str, object]
) -> None:
    """Unknown providers, unknown tiers, and omitted tiers cannot be silently defaulted."""
    path = _write(tmp_path, replacement)
    errors = validate_config(path)
    assert errors
    assert all(error.startswith("custom-routing.yaml:") for error in errors)
    with pytest.raises(ValidationError):
        load_config(path)


def test_configuration_when_file_invalid_never_falls_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, db: Database
) -> None:
    """An explicit nonexistent environment override also fails conversation startup."""
    missing = tmp_path / "missing.yaml"
    monkeypatch.setenv("DATAKEEL_MODEL_ROUTING_FILE", str(missing))
    assert "document" in validate_config()[0]
    with pytest.raises(ValidationError, match=r"missing\.yaml"):
        create_conversation(db, ConversationCreate())
    missing.write_text("[broken")
    assert "document" in validate_config()[0]


def test_configuration_when_fallback_cycle_or_foreign_model_rejects(tmp_path: Path) -> None:
    """Price ownership and cycle checks inspect every configured model and link."""
    config = load_config()
    fake = config.providers["fake"]
    providers = dict(config.providers)
    providers["fake"] = fake.model_copy(
        update={"fallbacks": {"fake-demo": "fake-script", "fake-script": "fake-demo"}}
    )
    path = _write(tmp_path, config.model_copy(update={"providers": providers}).model_dump())
    assert any("fallback cycle" in error for error in validate_config(path))
    providers["fake"] = fake.model_copy(
        update={"fallbacks": {"fake-demo": "gpt-4.1-mini", "missing": "fake-demo"}}
    )
    path = _write(tmp_path, config.model_copy(update={"providers": providers}).model_dump())
    errors = validate_config(path)
    assert any("another provider" in error for error in errors)
    assert any("no price" in error for error in errors)


def test_configuration_when_chain_exceeds_two_backups_rejects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Even fully priced same-provider chains remain bounded to two backups."""
    prices = load_prices()
    template = next(price for price in prices.models if price.model == "fake-demo")
    extended = prices.model_copy(
        update={
            "models": [
                *prices.models,
                *[
                    template.model_copy(update={"model": name})
                    for name in ("backup-one", "backup-two")
                ],
            ]
        }
    )
    monkeypatch.setattr("datakeel.routing.config.load_prices", lambda: extended)
    config = load_config()
    providers = dict(config.providers)
    providers["fake"] = providers["fake"].model_copy(
        update={
            "fallbacks": {
                "fake-demo": "fake-script",
                "fake-script": "backup-one",
                "backup-one": "backup-two",
            }
        }
    )
    path = _write(tmp_path, config.model_copy(update={"providers": providers}).model_dump())
    assert any("more than two backups" in error for error in validate_config(path))
    assert fallback_chain(providers["fake"], "fake-demo") == [
        "fake-demo",
        "fake-script",
        "backup-one",
    ]


def test_chain_when_cycle_is_supplied_remains_bounded() -> None:
    """Defensive traversal cannot hang even before full configuration validation."""
    models = ProviderModels(
        tiers=TierModels(simple="one", multi_step="one", high_risk="one"),
        fallbacks={"one": "two", "two": "one"},
    )
    assert fallback_chain(models, "one") == ["one", "two"]


def test_tiered_example_configuration_when_loaded_routes_tiers_and_fallbacks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The bundled tiered-and-backup example validates cleanly across providers and endpoints."""
    example = contract_path("routing/models-tiered.example.yaml")
    assert validate_config(example) == []
    config = load_config(example)

    openai_auto = ConversationCreate(provider="openai", model="auto")
    simple = select_model(openai_auto, TierState(), config)
    multi = select_model(openai_auto, TierState(response_has_tool_result=True), config)
    high_risk = select_model(openai_auto, TierState(response_has_plan=True), config)
    assert (simple.model, simple.pinned) == ("gpt-4.1-nano", False)
    assert (multi.model, multi.pinned) == ("gpt-4.1-mini", False)
    assert (high_risk.model, high_risk.pinned) == ("gpt-4.1", False)
    assert model_chain(openai_auto, high_risk, config) == [
        "gpt-4.1",
        "gpt-4.1-mini",
        "gpt-4.1-nano",
    ]

    anthropic_auto = ConversationCreate(provider="anthropic", model="auto")
    anthropic_high = select_model(anthropic_auto, TierState(response_has_plan=True), config)
    assert anthropic_high.model == "claude-sonnet-4-5-20250929"
    assert model_chain(anthropic_auto, anthropic_high, config) == [
        "claude-sonnet-4-5-20250929",
        "claude-sonnet-4-20250514",
        "claude-haiku-4-5-20251001",
    ]

    monkeypatch.setenv("DATAKEEL_OPENAI_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode")
    bailian = load_config(example)
    assert bailian.providers["openai"].tiers.high_risk == "qwen3.8-max"
    assert fallback_chain(bailian.providers["openai"], "qwen3.8-max") == [
        "qwen3.8-max",
        "qwen3.7-plus",
        "qwen3.5-flash",
    ]
