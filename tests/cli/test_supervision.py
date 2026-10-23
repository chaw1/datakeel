# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Demo supervision cleans child processes after startup and interruption failures."""

from __future__ import annotations

import argparse
import importlib
import subprocess
from types import SimpleNamespace
from typing import TYPE_CHECKING, Never

import pytest

from datakeel.core.errors import ExecutionError
from datakeel.worker.runner import run_worker

if TYPE_CHECKING:
    from pathlib import Path

    from datakeel.storage.database import Database

module = importlib.import_module("datakeel.cli.demo")


class Child:
    """Controllable child-process contract without launching another process."""

    def __init__(self, *, exited: bool = False, timeout: bool = False) -> None:
        """Configure the child's exit and termination behavior."""
        self.exited = exited
        self.timeout = timeout
        self.terminated = False
        self.killed = False
        self.waits = 0

    def poll(self) -> int | None:
        """Provide the poll test fixture."""
        return 1 if self.exited else None

    def terminate(self) -> None:
        """Provide the terminate test fixture."""
        self.terminated = True

    def wait(self, timeout: float | None = None) -> int:
        """Provide the wait test fixture."""
        self.waits += 1
        if timeout and self.timeout:
            msg = "fixture-child"
            raise subprocess.TimeoutExpired(msg, timeout)
        return 0

    def kill(self) -> None:
        """Provide the kill test fixture."""
        self.killed = True


@pytest.fixture
def supervised(db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> argparse.Namespace:
    """Provide the supervised test fixture."""
    source = tmp_path / "generated.txt"
    source.write_text("Generated observation", encoding="utf-8")
    monkeypatch.setattr(module, "generate_samples", lambda _directory: [source])
    monkeypatch.setattr(module, "Database", lambda: db)
    previous_handlers = []
    monkeypatch.setattr(module.signal, "signal", lambda *_args: previous_handlers.append(_args))
    return argparse.Namespace(once=False, host="127.0.0.1", port=8765, legacy_only=True)


def test_supervision_when_child_exits_during_startup_raises_and_reaps(
    supervised: argparse.Namespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify supervision when child exits during startup raises and reaps."""
    children = [Child(exited=True), Child()]
    pending = iter(children)
    monkeypatch.setattr(module.subprocess, "Popen", lambda *_args: next(pending))
    with pytest.raises(ExecutionError, match="exited during startup"):
        module.demo(supervised)
    assert children[1].terminated is True
    assert [child.waits for child in children] == [1, 1]


def test_supervision_when_startup_deadline_elapsed_stops_children(
    supervised: argparse.Namespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify supervision when startup deadline elapsed stops children."""
    children = [Child(), Child()]
    pending, timestamps = iter(children), iter([0, 70])
    monkeypatch.setattr(module.subprocess, "Popen", lambda *_args: next(pending))
    monkeypatch.setattr(module, "time", SimpleNamespace(monotonic=lambda: next(timestamps)))
    with pytest.raises(ExecutionError, match="within 60 seconds"):
        module.demo(supervised)
    assert all(child.terminated for child in children)


def test_supervision_when_interrupted_kills_child_that_ignores_termination(
    db: Database, supervised: argparse.Namespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify supervision when interrupted kills child that ignores termination."""
    module.seed_demo(db)
    run_worker(db, once=True)
    children = [Child(timeout=True), Child()]
    pending = iter(children)
    monkeypatch.setattr(module.subprocess, "Popen", lambda *_args: next(pending))
    client = SimpleNamespace(get=lambda _path: SimpleNamespace(is_success=True))

    class ReadyClient:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            """Accept the HTTP client's constructor arguments without networking."""

        def __enter__(self) -> SimpleNamespace:
            return client

        def __exit__(self, *_args: object) -> None:
            return None

    def interrupt(_seconds: float) -> Never:
        """Provide the interrupt test fixture."""
        raise KeyboardInterrupt

    monkeypatch.setattr(module, "Client", ReadyClient)
    monkeypatch.setattr(module, "time", SimpleNamespace(monotonic=lambda: 0, sleep=interrupt))
    module.demo(supervised)
    assert children[0].killed is True
    assert children[0].waits == 2
