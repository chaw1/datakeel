# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""YAML code values must remain representable by the strict JSON API."""

import math
from pathlib import Path

import pytest
from pydantic import ValidationError as ModelValidationError

from datakeel.core.errors import ValidationError
from datakeel.core.standard_models import CodeEntry
from datakeel.standards.loader import load_contract


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_nonfinite_code_values_are_rejected_before_persistence(value: float) -> None:
    """A value that would make JSON responses fail cannot enter the effective contract."""
    with pytest.raises(ModelValidationError):
        CodeEntry(value=value, label_zh="生成值", label_en="Generated value")


@pytest.mark.parametrize("value", [".nan", ".inf", "-.inf"])
def test_yaml_nonfinite_reference_values_fail_import(tmp_path: Path, value: str) -> None:
    """Safe YAML numeric syntax is still checked against the JSON scalar boundary."""
    path = tmp_path / "reference.yaml"
    path.write_text(
        "code_lists:\n- code: states\n  name: States\n  entries:\n"
        f"  - value: {value}\n    label_zh: 生成值\n    label_en: Generated value\n",
        encoding="utf-8",
    )
    with pytest.raises(ValidationError, match="Invalid standards contract"):
        load_contract(path)
