# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Shared independently generated enterprise standards fixtures."""

from pathlib import Path

import pytest

from datakeel.core.standard_models import StandardsContract
from datakeel.standards.loader import load_contract


@pytest.fixture
def contract() -> StandardsContract:
    """Load the public bilingual example contract through its real validator."""
    return load_contract(Path(__file__).resolve().parents[2] / "contracts/standards")
