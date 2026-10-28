# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Quality tool goldens assert actual worker-produced observations and trends."""

import socket
from pathlib import Path

import pytest

from datakeel.harness.cases import load_cases
from datakeel.harness.dq_cases import seed_quality_case
from datakeel.harness.execution import run_case
from datakeel.storage.database import Database
from datakeel.storage.dq_reads import read_results


def test_failed_quality_golden_uses_real_rule_results(monkeypatch: pytest.MonkeyPatch) -> None:
    """The failure-list golden reads a real failed scan without network or model access."""

    def forbidden(*args: object, **kwargs: object) -> None:
        del args, kwargs
        pytest.fail("Quality golden attempted network access")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    case = next(item for item in load_cases() if item.id == "44-quality-failures")
    report = run_case(case, "fake")
    assert report.passed, report.failures


def test_table_quality_golden_uses_real_history() -> None:
    """The table golden asserts the measured score and both two-point rule histories."""
    case = next(item for item in load_cases() if item.id == "45-quality-table-history")
    report = run_case(case, "fake")
    assert report.passed, report.failures


def test_quality_fixture_runs_approved_definitions_and_merges_incidents(
    db: Database, tmp_path: Path
) -> None:
    """Fixture setup uses production action and worker paths on either fact-store stack."""
    fixture = seed_quality_case(db, tmp_path)
    assert fixture.dataset_id
    assert [result.status for result in read_results(db, "orders-amount")] == ["failed", "failed"]
    assert [result.status for result in read_results(db, "orders-id")] == ["passed", "passed"]
