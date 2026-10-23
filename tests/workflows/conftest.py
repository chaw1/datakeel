# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Isolate workflow data and advance durable workers through injectable wait hooks."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from datakeel.storage.dataset_service import import_paths
from datakeel.worker.runner import run_worker
from datakeel.workflows.execution import WorkflowHooks

if TYPE_CHECKING:
    from pathlib import Path

    from datakeel.storage.database import Database
    from datakeel.storage.views import DatasetView


class ManualClock:
    """Advance a monotonic test clock without sleeping in real time."""

    def __init__(self) -> None:
        """Start each isolated run at zero elapsed seconds."""
        self.value = 0.0

    def now(self) -> float:
        """Read deterministic elapsed seconds."""
        return self.value

    def sleep(self, seconds: float) -> None:
        """Advance by a requested poll interval without blocking."""
        self.value += seconds


def worker_hooks(db: Database) -> WorkflowHooks:
    """Drain the real durable worker from the first polling sleep."""
    clock = ManualClock()

    def advance(seconds: float) -> None:
        run_worker(db, once=True)
        clock.sleep(seconds)

    return WorkflowHooks(clock=clock.now, sleep=advance)


def create_dataset(db: Database, directory: Path) -> DatasetView:
    """Use a separate two-file dataset instead of modifying the demonstration corpus."""
    directory.mkdir(parents=True, exist_ok=True)
    paths = [directory / "empty.txt", directory / "healthy.txt"]
    paths[0].write_text("", encoding="utf-8")
    paths[1].write_text(
        "A complete generated sample containing useful quality evidence.", encoding="utf-8"
    )
    return import_paths(db, "workflow-fixture", paths)


@pytest.fixture(autouse=True)
def offline_reports(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prevent optional report enrichment from reaching an inherited provider URL."""
    monkeypatch.delenv("DATAKEEL_LLM_URL", raising=False)


@pytest.fixture
def dataset(db: Database, tmp_path: Path) -> DatasetView:
    """Provide independently imported low and high quality samples for every test."""
    return create_dataset(db, tmp_path / "workflow-data")
