# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Large local fixture preparation must not consume the child-server readiness window."""

import argparse
import importlib
from unittest.mock import MagicMock

import pytest

from datakeel.core.errors import ExecutionError
from datakeel.storage.database import Database

module = importlib.import_module("datakeel.cli.demo")


def test_server_gets_its_readiness_window_after_slow_fixture_generation(
    db: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A ready server is probed even after fixture generation took over sixty seconds."""
    worker, server = MagicMock(), MagicMock()
    worker.poll.side_effect = [None, 0]
    server.poll.return_value = None
    monkeypatch.setattr(module.subprocess, "Popen", MagicMock(side_effect=[worker, server]))
    monkeypatch.setattr(module.time, "monotonic", lambda: 100)
    monkeypatch.setattr(module, "_check_task", lambda *_args: True)
    monkeypatch.setattr(module, "_stop", lambda *_args: None)
    client = MagicMock()
    client.__enter__.return_value = client
    client.get.return_value.is_success = True
    monkeypatch.setattr(module, "Client", MagicMock(return_value=client))
    with pytest.raises(ExecutionError, match="API or worker exited"):
        module._serve(  # noqa: SLF001  # Exercise actual readiness supervision without processes.
            db, "task", argparse.Namespace(host="127.0.0.1", port=8817), 0
        )
    client.get.assert_called_once_with("/api/health")
