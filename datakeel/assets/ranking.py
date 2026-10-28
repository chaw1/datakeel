# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Load fixed default asset ranking weights from the checkout or packaged contract."""

from pathlib import Path

import yaml
from pydantic import ValidationError as ModelValidationError

from datakeel.core.data_asset_models import AssetRanking
from datakeel.core.errors import ValidationError


def ranking_path() -> Path:
    """Locate the fixed default contract in the checkout or packaged wheel."""
    package = Path(__file__).resolve().parents[1]
    source = package.parent / "contracts" / "assets" / "ranking.yaml"
    return source if source.exists() else package / "_contracts" / "assets" / "ranking.yaml"


def load_ranking(path: Path | None = None) -> AssetRanking:
    """Fail explicitly for an invalid contract rather than silently change ordering."""
    selected = path or ranking_path()
    try:
        return AssetRanking.model_validate(yaml.safe_load(selected.read_text()))
    except (OSError, yaml.YAMLError, ModelValidationError) as exc:
        msg = f"Invalid asset ranking contract: {selected.name}"
        raise ValidationError(msg) from exc
