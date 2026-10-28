# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Recipient CLI stays independent of settings, database and model services."""

import json
import sys
from pathlib import Path

import pytest

from datakeel import cli


def test_offline_cli_ignores_invalid_service_settings_and_database(
    package: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Even invalid platform configuration cannot prevent local recipient verification."""

    def forbidden() -> None:
        pytest.fail("Offline reconcile attempted platform initialization")

    monkeypatch.setenv("DATAKEEL_DATABASE_URL", "invalid-database")
    monkeypatch.setenv("DATAKEEL_MODEL_ROUTING_FILE", "/nonexistent-routing-file")
    monkeypatch.setattr(cli, "Database", forbidden)
    monkeypatch.setattr(cli, "configure_logging", forbidden)
    monkeypatch.setattr(cli, "load_config", forbidden)
    monkeypatch.setattr(sys, "argv", ["datakeel", "reconcile", str(package), "--json"])
    cli.main()
    result = json.loads(capsys.readouterr().out)
    assert result["passed"] is True
    assert len(result["categories"]) == 6


def test_offline_cli_corruption_exits_one_with_readable_differences(
    package: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Human-facing output is bilingual and unsuccessful delivery has a failing exit status."""
    (package / "files/0.txt").write_bytes(b"changed")
    monkeypatch.setattr(sys, "argv", ["datakeel", "reconcile", str(package)])
    with pytest.raises(SystemExit) as error:
        cli.main()
    assert error.value.code == 1
    output = capsys.readouterr().out
    assert "FAIL" in output
    assert "内容哈希" in output
    assert "files/0.txt" in output


def test_invalid_delivery_cli_exits_two_without_dumping_input(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Malformed contracts yield a useful machine error without exposing their contents."""
    (tmp_path / "MANIFEST.json").write_text('{"private": "sensitive-input"}')
    monkeypatch.setattr(sys, "argv", ["datakeel", "reconcile", str(tmp_path), "--json"])
    with pytest.raises(SystemExit) as error:
        cli.main()
    assert error.value.code == 2
    output = capsys.readouterr().out
    assert json.loads(output)["error"] == "invalid_delivery"
    assert "sensitive-input" not in output
