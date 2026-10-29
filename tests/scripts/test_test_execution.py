# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Validate the shared concurrency contract and the full-suite pytest entry point."""

from __future__ import annotations

import pytest

from scripts import run_pytest, test_workers


@pytest.mark.parametrize(
    ("cpus", "expected"), [(None, 1), (0, 1), (1, 1), (4, 4), (15, 15), (64, 16)]
)
def test_default_workers_respect_available_cpus_and_resource_cap(
    monkeypatch: pytest.MonkeyPatch, cpus: int | None, expected: int
) -> None:
    """Unknown CPU counts remain usable and large machines stay bounded."""
    monkeypatch.delenv("DATAKEEL_TEST_WORKERS", raising=False)
    monkeypatch.setattr(test_workers.os, "cpu_count", lambda: cpus)
    assert test_workers.test_worker_count() == expected


@pytest.mark.parametrize("value", ["1", "4", "24"])
def test_explicit_workers_override_the_default(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    """A deliberate positive override applies to both test executors."""
    monkeypatch.setenv("DATAKEEL_TEST_WORKERS", value)
    assert test_workers.test_worker_count() == int(value)


@pytest.mark.parametrize("value", ["", "0", "-1", "auto", "1.5"])
def test_invalid_worker_counts_fail_closed(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    """Configuration mistakes must not silently select an unbounded worker count."""
    monkeypatch.setenv("DATAKEEL_TEST_WORKERS", value)
    with pytest.raises(ValueError, match="must be a positive integer"):
        test_workers.test_worker_count()


@pytest.mark.parametrize(("workers", "xdist_count"), [(1, "0"), (4, "4")])
def test_pytest_entry_preserves_selection_reports_and_exit_status(
    monkeypatch: pytest.MonkeyPatch, workers: int, xdist_count: str
) -> None:
    """Only scheduling arguments change; every pytest failure remains a gate failure."""
    observed: list[list[str]] = []

    def execute(arguments: list[str]) -> int:
        observed.append(arguments)
        return 1

    monkeypatch.setenv("DATAKEEL_TEST_WORKERS", str(workers))
    monkeypatch.setattr(
        run_pytest.sys, "argv", ["run_pytest", "--cov=datakeel", "--cov-fail-under=85"]
    )
    monkeypatch.setattr(run_pytest.pytest, "main", execute)
    with pytest.raises(SystemExit) as stopped:
        run_pytest.main()
    assert stopped.value.code == 1
    assert observed == [
        ["--cov=datakeel", "--cov-fail-under=85", "-n", xdist_count, "--dist=loadfile"]
    ]
