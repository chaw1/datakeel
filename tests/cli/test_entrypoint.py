# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""The Python module entry point dispatches the same public command function."""

from __future__ import annotations

import runpy
from typing import TYPE_CHECKING

from datakeel import cli

if TYPE_CHECKING:
    import pytest


def test_module_entrypoint_when_executed_dispatches_main(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify module entrypoint when executed dispatches main."""
    calls = []
    monkeypatch.setattr(cli, "main", lambda: calls.append("main"))
    runpy.run_module("datakeel.cli.__main__", run_name="__main__")
    assert calls == ["main"]
