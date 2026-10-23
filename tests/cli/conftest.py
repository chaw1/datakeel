# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Isolate command-line effects to the per-test database."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING, Protocol

import pytest

from datakeel import cli

if TYPE_CHECKING:
    from datakeel.storage.database import Database


class Invoke(Protocol):
    """Run one CLI invocation using a sequence of string arguments."""

    def __call__(self, *arguments: str) -> None:
        """Invoke the command with isolated environment and database effects."""
        ...


@pytest.fixture
def invoke(db: Database, monkeypatch: pytest.MonkeyPatch) -> Invoke:
    """Provide the invoke test fixture."""
    monkeypatch.setattr(cli, "Database", lambda: db)
    monkeypatch.setattr(cli, "configure_logging", lambda: None)

    def run(*arguments: str) -> None:
        """Provide the run test fixture."""
        monkeypatch.setattr(sys, "argv", ["datakeel", *arguments])
        cli.main()

    return run
