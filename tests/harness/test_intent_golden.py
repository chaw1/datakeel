# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""One-sentence golden cases cover multi-step plans, clarification and overreach."""

import pytest

from datakeel.harness.cases import load_cases
from datakeel.harness.execution import run_case

CASES = ("48-one-sentence-multistep", "48-one-sentence-clarify", "48-one-sentence-overreach")


@pytest.mark.parametrize("identifier", CASES)
def test_one_sentence_golden_passes_offline(identifier: str) -> None:
    """Each case runs against the real runtime with a scripted planner and no network."""
    case = next(item for item in load_cases() if item.id == identifier)
    report = run_case(case, "fake")
    assert report.passed, report.failures
    assert report.intent_kinds
