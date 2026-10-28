# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""An ungranted real Agent run may explain application, never expose source values."""

from datakeel.harness.cases import load_cases
from datakeel.harness.execution import run_case


def test_ungranted_agent_guides_application_without_returning_values() -> None:
    """Inspect measured tool and provider context rather than trusting scripted prose alone."""
    case = next(item for item in load_cases() if item.id == "44-asset-access")
    result = run_case(case, "fake")
    assert result.passed, result.failures
    assert result.tool_results[0].status == "FAILED"
    assert result.tool_results[0].content.root == {}
    assert "申请" in result.final_answer
