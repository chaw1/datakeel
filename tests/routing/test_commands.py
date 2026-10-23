# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Local routing command output contains exact accuracy and inspectable confusion counts."""

import argparse
import json
from pathlib import Path

import pytest

from datakeel.cli.routing import dispatch, register_parser
from datakeel.routing.evaluation import evaluate_routes


def _arguments(arguments: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    register_parser(parser.add_subparsers(dest="command", required=True))
    return parser.parse_args(arguments)


def test_eval_command_when_offline_prints_accuracy_and_confusion(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Both human and machine output retain all three separate confusion matrices."""
    dispatch(_arguments(["eval-route"]))
    output = capsys.readouterr().out
    assert "100%" in output
    assert all(f"{name} confusion matrix" in output for name in ("Workflow", "Branch", "Tier"))
    dispatch(_arguments(["eval-route", "--json"]))
    assert json.loads(capsys.readouterr().out)["accuracy"] == 1


def test_config_command_when_valid_or_missing_reports_explicit_status(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """An explicit invalid path yields errors instead of loading defaults."""
    dispatch(_arguments(["routing", "validate"]))
    assert "is valid" in capsys.readouterr().out
    with pytest.raises(SystemExit, match="1"):
        dispatch(_arguments(["routing", "validate", str(tmp_path / "missing.yaml")]))
    assert "missing.yaml:document" in capsys.readouterr().out


def test_eval_command_when_labels_diverge_returns_failure(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """CLI exit status cannot hide a failed route even when reporting still succeeds."""
    failed = evaluate_routes().model_copy(
        update={"failures": ["fixture mismatch"], "intent_correct": 74}
    )
    monkeypatch.setattr("datakeel.cli.routing.evaluate_routes", lambda: failed)
    with pytest.raises(SystemExit, match="1"):
        dispatch(_arguments(["eval-route"]))
    assert "fixture mismatch" in capsys.readouterr().out
