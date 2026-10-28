# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""The README negative check accepts only safe, explicit asset refusals."""

import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest

from scripts.check_readme import verify_denied_command

_REFUSAL = "AuthorizationError: Asset fixture requires an active export grant; apply for access"


def _fixed_result(
    result: subprocess.CompletedProcess[str],
) -> Callable[[list[str], dict[str, str]], subprocess.CompletedProcess[str]]:
    def run(
        _arguments: list[str], _environment: dict[str, str]
    ) -> subprocess.CompletedProcess[str]:
        return result

    return run


@pytest.mark.parametrize(
    ("returncode", "stdout", "stderr", "artifact"),
    [
        (0, "", _REFUSAL, False),
        (1, "unexpected data", _REFUSAL, False),
        (1, "", "RuntimeError: broken environment", False),
        (1, "", _REFUSAL, True),
    ],
)
def test_readme_denial_rejects_success_data_other_errors_and_partial_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    returncode: int,
    stdout: str,
    stderr: str,
    *,
    artifact: bool,
) -> None:
    """A failing command alone cannot count as a successful permission test."""
    result = subprocess.CompletedProcess(["fixture"], returncode, stdout=stdout, stderr=stderr)
    monkeypatch.setattr("scripts.check_readme.run_command", _fixed_result(result))
    output = tmp_path / "export.json"
    if artifact:
        output.write_text("partial data", encoding="utf-8")
    with pytest.raises(RuntimeError, match="authorization refusal"):
        verify_denied_command(["export"], {}, output)


def test_readme_denial_accepts_only_typed_permission_refusal_without_data(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An explicit nonzero authorization refusal with empty stdout and no file is expected."""
    result = subprocess.CompletedProcess(["fixture"], 1, stdout="", stderr=_REFUSAL)
    monkeypatch.setattr("scripts.check_readme.run_command", _fixed_result(result))
    verify_denied_command(["export"], {}, tmp_path / "absent.json")
