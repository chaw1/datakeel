# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Extended fixtures remain deterministic and expose script ownership mistakes as failures."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from datakeel.core.errors import ExecutionError
from datakeel.core.harness_eval import GoldenExpect
from datakeel.harness.cases import load_cases
from datakeel.harness.execution import run_case
from datakeel.harness.injection_cases import seed_injection_case

if TYPE_CHECKING:
    from pathlib import Path

    from datakeel.storage.database import Database


def test_script_agent_mismatch_fails_even_when_provider_error_is_expected() -> None:
    """A permissive stop expectation cannot turn a misrouted scripted reply into a pass."""
    case = next(case for case in load_cases() if case.id == "32-canary-prefix")
    turn = case.turns[0].model_copy(
        update={"script": [case.turns[0].script[0].model_copy(update={"agent": "wrong-agent"})]}
    )
    case = case.model_copy(
        update={
            "turns": [turn],
            "expect": GoldenExpect(stop_contains=["provider_error"], max_tokens=10000),
        }
    )
    result = run_case(case, "fake")
    assert not result.passed
    assert any("wrong-agent" in failure for failure in result.failures)


def test_packaged_scripts_keep_identical_ids_between_loads() -> None:
    """Default random call identities must not make unchanged golden suites drift."""
    assert [case.model_dump() for case in load_cases()] == [
        case.model_dump() for case in load_cases()
    ]


def test_injection_fixture_reports_extraction_failure(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A missing worker lease cannot leave an unextracted fixture counted as a policy test."""
    monkeypatch.setattr("datakeel.harness.injection_cases.DatabaseQueue.claim", lambda _self: None)
    with pytest.raises(ExecutionError, match="Injection fixture extraction failed"):
        seed_injection_case(db, tmp_path)


def test_memory_observation_assertions_can_fail_independently() -> None:
    """Presence, deletion and forbidden context assertions inspect runtime observations."""
    case = next(case for case in load_cases() if case.id == "31-memory-minimum-overlap")
    expected = case.expect.model_copy(
        update={"memory_count": 0, "memory_used": True, "context_not_contains": ["Catalog"]}
    )
    result = run_case(case.model_copy(update={"expect": expected}), "fake")
    assert not result.passed
    assert any("Active memory count" in failure for failure in result.failures)
    assert any("Memory context present" in failure for failure in result.failures)
    assert any("forbidden text" in failure for failure in result.failures)
