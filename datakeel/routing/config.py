# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Load explicit provider routes and validate every priced fallback chain locally."""

from pathlib import Path

import yaml
from pydantic import ValidationError as ModelValidationError

from datakeel.core.errors import ValidationError
from datakeel.core.harness_pricing import ModelPrice, PriceTable
from datakeel.core.settings import get_settings
from datakeel.routing.models import ModelRoutingConfig, ProviderModels

MAX_BACKUPS = 2


def contract_path(name: str) -> Path:
    """Resolve the same contract from a checkout or an installed wheel."""
    package = Path(__file__).resolve().parents[1]
    source = package.parent / "contracts" / name
    return source if source.exists() else package / "_contracts" / name


def load_prices() -> PriceTable:
    """Read the checked-in tariff without contacting a model service."""
    return PriceTable.model_validate(yaml.safe_load(contract_path("model-prices.yaml").read_text()))


def price_for(model: str) -> tuple[str, ModelPrice]:
    """Require a declared price before any invocation reserves budget."""
    table = load_prices()
    for price in table.models:
        if price.model == model:
            return table.version_date.isoformat(), price
    msg = f"No price configured for model: {model}"
    raise ValidationError(msg)


def fallback_chain(config: ProviderModels, model: str) -> list[str]:
    """Return a bounded chain after whole-document validation has succeeded."""
    chain = [model]
    while model in config.fallbacks:
        model = config.fallbacks[model]
        if model in chain or len(chain) > MAX_BACKUPS:
            break
        chain.append(model)
    return chain


def _provider_errors(provider: str, config: ProviderModels, prices: PriceTable) -> list[str]:
    models = {config.tiers.simple, config.tiers.multi_step, config.tiers.high_risk}
    models.update(config.fallbacks)
    models.update(config.fallbacks.values())
    declared = {price.model: price.provider for price in prices.models}
    errors: list[str] = []
    for model in sorted(models):
        location = f"providers.{provider}.models.{model}"
        if model not in declared:
            errors.append(f"{location}: model has no price")
        elif declared[model] != provider:
            errors.append(f"{location}: model belongs to another provider")
        seen = {model}
        current = model
        while current in config.fallbacks:
            current = config.fallbacks[current]
            if current in seen:
                errors.append(f"providers.{provider}.fallbacks.{model}: fallback cycle")
                break
            seen.add(current)
            if len(seen) > MAX_BACKUPS + 1:
                errors.append(f"providers.{provider}.fallbacks.{model}: more than two backups")
                break
    return errors


def _read(path: Path) -> tuple[ModelRoutingConfig | None, list[str]]:
    try:
        config = ModelRoutingConfig.model_validate(yaml.safe_load(path.read_text()))
    except ModelValidationError as error:
        return None, [
            f"{path.name}:{'.'.join(map(str, item['loc']))}: {item['msg']}"
            for item in error.errors()
        ]
    except (OSError, yaml.YAMLError) as error:
        return None, [f"{path.name}:document: {error}"]
    errors = [
        f"providers.{provider}: missing provider configuration"
        for provider in ("fake", "openai", "anthropic")
        if provider not in config.providers
    ]
    prices = load_prices()
    for provider, settings in config.providers.items():
        errors.extend(_provider_errors(provider, settings, prices))
    return config, [f"{path.name}:{error}" for error in errors]


def routing_path(path: Path | None = None) -> Path:
    """Honor an explicit environment path, including when it does not exist."""
    return path or get_settings().model_routing_file or contract_path("routing/models.yaml")


def validate_config(path: Path | None = None) -> list[str]:
    """Return located errors suitable for CLI reporting and mutation assertions."""
    return _read(routing_path(path))[1]


def load_config(path: Path | None = None) -> ModelRoutingConfig:
    """Reject invalid routing configuration instead of falling back to defaults."""
    config, errors = _read(routing_path(path))
    if config is None or errors:
        raise ValidationError("; ".join(errors))
    return config
