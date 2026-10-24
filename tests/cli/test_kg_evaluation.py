# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""CLI evaluations default to offline replay and persist complete typed history."""

import argparse
import json
import socket
from pathlib import Path

import pytest
import yaml

from datakeel.cli.kg_evaluation import evaluate, register_parser
from datakeel.core.errors import ConflictError, NotFoundError, ValidationError
from datakeel.kg.loader import contracts_path, get_profile
from datakeel.storage.database import Database
from datakeel.storage.kg_evaluations import get_evaluation, list_evaluations, save_evaluation


def test_parser_defaults_are_offline_and_external_cases_are_explicit() -> None:
    """Expose both replay profile selection and arbitrary same-schema case paths."""
    parser = argparse.ArgumentParser()
    register_parser(parser.add_subparsers(dest="command"))
    args = parser.parse_args(["eval-kg"])
    assert args.profile == "replay-demo"
    assert args.cases is None
    args = parser.parse_args(
        ["eval-kg", "--profile", "replay-flash", "--cases", "custom.yaml", "--json"]
    )
    assert args.profile == "replay-flash"
    assert args.cases == Path("custom.yaml")
    assert args.json_output


def test_default_evaluation_opens_no_network_and_persists_history(
    db: Database, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Socket and secret guards cover the actual default CLI execution path."""

    def forbidden(*args: object, **kwargs: object) -> None:
        del args, kwargs
        pytest.fail("Offline graph evaluation attempted network or credential access")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr("datakeel.extraction_runtime.factory.get_settings", forbidden)
    report = evaluate(db, json_output=True)
    output = json.loads(capsys.readouterr().out)
    assert output["id"] == report.id
    assert output["recording"]["all"]["relation_strict"]["f1"] == 0.865
    assert get_evaluation(db, report.id) == report
    assert list_evaluations(db) == (report,)
    assert save_evaluation(db, report) == report
    with pytest.raises(ConflictError, match="identity cannot be replaced"):
        save_evaluation(db, report.model_copy(update={"model": "changed"}))


def test_cli_human_output_and_custom_profile_file(
    db: Database, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Resolve a profile's relative replay file from that profile's directory."""
    profile = get_profile("replay-flash")
    path = tmp_path / "profile.yaml"
    assert profile.recording
    recording = tmp_path / "recording.yaml"
    recording.write_bytes((contracts_path() / profile.recording).read_bytes())
    path.write_text(
        yaml.safe_dump(
            profile.model_copy(update={"recording": "recording.yaml"}).model_dump(mode="json")
        )
    )
    report = evaluate(db, str(path))
    output = capsys.readouterr().out
    assert "Product / all" in output
    assert "candidates" in output
    assert "Saved evaluation" in output
    assert report.product.all.relation_strict.f1 == 1


@pytest.mark.parametrize("limit", [0, 1001])
def test_history_rejects_unbounded_requests(db: Database, limit: int) -> None:
    """Keep the read-only history query bounded."""
    with pytest.raises(ValidationError, match="history limit"):
        list_evaluations(db, limit)


def test_history_missing_identity_is_explicit(db: Database) -> None:
    """Return a typed not-found error instead of a fabricated empty report."""
    with pytest.raises(NotFoundError):
        get_evaluation(db, "absent")
