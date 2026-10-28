# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Load versioned YAML quality contracts through the shared frozen boundary model."""

from pathlib import Path

import yaml
from pydantic import ValidationError as ModelValidationError

from datakeel.core.dq_models import DqContract
from datakeel.core.errors import ValidationError


def load_contract(path: Path) -> DqContract:
    """Validate a complete local contract without writing or opening business sources."""
    try:
        return DqContract.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
    except (OSError, yaml.YAMLError, ModelValidationError) as error:
        msg = "Invalid quality-rule YAML contract"
        raise ValidationError(msg) from error
