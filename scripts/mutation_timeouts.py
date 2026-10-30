# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Survive mutation subprocess timeouts: retry once, then record an environment failure."""

from __future__ import annotations

import shlex
import subprocess
from typing import TYPE_CHECKING

from rich.console import Console

from datakeel.core.models import BoundaryModel

if TYPE_CHECKING:
    from collections.abc import Callable


class EnvironmentFailure(BoundaryModel):
    """A measurement that timed out twice: no evidence either way, and never a kill."""

    target: str
    command: str
    timeout_seconds: float
    attempts: int = 2

    def describe(self) -> str:
        """One line naming the target and the command, for logs without a stack trace."""
        return (
            f"Environment failure: {self.target}: command `{self.command}` timed out after "
            f"{self.timeout_seconds:g} seconds on all {self.attempts} attempts"
        )


def _console() -> Console:
    return Console(soft_wrap=True, highlight=False)


def _command(error: subprocess.TimeoutExpired) -> str:
    command = error.cmd
    if isinstance(command, (list, tuple)):
        return shlex.join(str(part) for part in command)
    return str(command)


def retry_on_timeout[Result](
    operation: Callable[[], Result], target: str
) -> Result | EnvironmentFailure:
    """Run a fresh measurement again after one timeout; a second timeout is environmental."""
    try:
        return operation()
    except subprocess.TimeoutExpired as error:
        _console().print(
            f"Retrying {target}: command `{_command(error)}` timed out after "
            f"{error.timeout:g} seconds",
            markup=False,
        )
    try:
        return operation()
    except subprocess.TimeoutExpired as error:
        return EnvironmentFailure(
            target=target, command=_command(error), timeout_seconds=error.timeout
        )
