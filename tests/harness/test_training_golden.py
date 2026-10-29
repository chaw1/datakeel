# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Training questions are answered from real local measurements through discovered reads."""

import pytest

from datakeel.harness.cases import load_cases
from datakeel.harness.execution import run_case


@pytest.mark.parametrize("identifier", ["46-training-distribution", "47-training-leakage"])
def test_training_golden_measures_version_facts(identifier: str) -> None:
    """Scripted words alone cannot satisfy counts, membership and direct-pair assertions."""
    case = next(item for item in load_cases() if item.id == identifier)
    result = run_case(case, "fake")
    assert result.passed, result.failures
