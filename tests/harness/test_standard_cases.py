# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""New standards goldens assert measured tool data through the real offline conversation graph."""

import pytest

from datakeel.core.harness_eval import GoldenCase
from datakeel.harness.cases import load_cases
from datakeel.harness.execution import run_case


@pytest.mark.parametrize(
    "case", [item for item in load_cases() if item.fixture_kind == "standards"]
)
def test_standards_goldens_read_confirmed_coverage_and_usage(case: GoldenCase) -> None:
    """A scripted answer cannot compensate for incorrect real coverage or usage data."""
    result = run_case(case, "fake")
    assert result.passed, result.failures
    assert len(result.tool_results) == 1
    assert result.tool_results[0].asset_refs
