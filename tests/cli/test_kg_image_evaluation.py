# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Image evaluation CLI keeps model selections separate and saves comparable history."""

import argparse
import json
import socket
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest
import yaml

from datakeel.cli import _evaluation_command
from datakeel.cli.kg_evaluation import register_parser
from datakeel.cli.kg_image_evaluation import evaluate
from datakeel.core.errors import BudgetError
from datakeel.core.harness_models import BudgetLimits
from datakeel.core.kg_image_request import ImageEvaluationRequest
from datakeel.core.transcription_models import TranscriptionResult
from datakeel.kg.loader import contracts_path, get_schema
from datakeel.kg_eval.image_loader import image_path, load_image_cases
from datakeel.storage.database import Database
from datakeel.storage.evidence_store import list_assertions
from datakeel.storage.harness_service import list_traces
from datakeel.storage.kg_evaluations import get_evaluation, list_evaluations
from datakeel.transcription.adapters import FakeTranscriber
from datakeel.transcription.loader import get_profile
from tests.kg.test_image_evaluation import archive, external_case


def test_cli_image_evaluation_is_offline_and_leaves_user_graph_untouched(
    db: Database,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Both score paths persist, but benchmark assertions stay in the isolated scoring store."""
    external_case(tmp_path)

    def forbidden(*_args: object, **_kwargs: object) -> None:
        pytest.fail("Offline image evaluation attempted a network connection or credential read")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr("datakeel.transcription.factory.get_settings", forbidden)
    monkeypatch.setattr("datakeel.extraction_runtime.factory.get_settings", forbidden)
    report = evaluate(db, ImageEvaluationRequest(cases=tmp_path), json_output=True)
    output = json.loads(capsys.readouterr().out)
    assert output["suite"] == "image"
    assert output["transcription_profile"] == "replay-image-demo"
    assert get_evaluation(db, report.id) == report
    assert list_assertions(db) == []
    assert report.image_product is not None
    assert report.image_recording is not None
    assert report.cost_usd == 0
    assert all(trace.call_type == "extraction" for trace in list_traces(db, report.id))


def test_cli_external_transcription_profile_resolves_relative_recording(
    db: Database,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A caller-controlled profile resolves its archive from its own directory."""
    external_case(tmp_path)
    profile = get_profile("replay-image-demo")
    assert profile.recording
    (tmp_path / "recording.yaml").write_bytes((contracts_path() / profile.recording).read_bytes())
    (tmp_path / "profile.yaml").write_text(
        yaml.safe_dump(
            profile.model_copy(update={"recording": "recording.yaml"}).model_dump(mode="json")
        )
    )
    report = evaluate(
        db,
        ImageEvaluationRequest(
            transcription_profile=str(tmp_path / "profile.yaml"), cases=tmp_path
        ),
    )
    output = capsys.readouterr().out
    assert "Recording" in output
    assert "Product" in output
    assert "Identifiers" in output
    assert report.product.all.relation_strict.tp > 0


def test_cli_image_flag_selects_image_defaults_and_persists(db: Database, tmp_path: Path) -> None:
    """The ordinary command dispatcher chooses image extraction only for the image suite."""
    external_case(tmp_path)
    parser = argparse.ArgumentParser()
    register_parser(parser.add_subparsers(dest="command"))
    args = parser.parse_args(["eval-kg", "--suite", "image", "--cases", str(tmp_path)])
    _evaluation_command(db, args)
    report = list_evaluations(db)[0]
    assert report.profile == "replay-image-flash"
    assert report.suite == "image"


def test_cli_image_budget_failure_does_not_publish_complete_report(
    db: Database, tmp_path: Path
) -> None:
    """Reserve image extraction before publishing a successful evaluation."""
    external_case(tmp_path)
    with pytest.raises(BudgetError):
        evaluate(
            db, ImageEvaluationRequest(cases=tmp_path), limits=BudgetLimits(conversation_tokens=0)
        )
    assert list_evaluations(db) == ()


def _visual_pair(tmp_path: Path) -> tuple[TranscriptionResult, ...]:
    suite, _, directory = load_image_cases(get_schema())
    selected = suite.cases[12:14]
    for case in selected:
        target = tmp_path / case.image
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(image_path(directory, case.image).read_bytes())
    (tmp_path / "cases.yaml").write_text(
        yaml.safe_dump(
            {"id": "two-images", "cases": [case.model_dump(mode="json") for case in selected]}
        )
    )
    profile = get_profile("replay-image-demo").model_copy(
        update={
            "backend": "vlm",
            "model": "unknown-fixture",
            "base_url": "http://localhost:11434/v1",
            "recording": None,
        }
    )
    (tmp_path / "profile.yaml").write_text(yaml.safe_dump(profile.model_dump(mode="json")))
    source = {record.image_hash: record for record in archive("qwen-image").records}
    return tuple(
        source[case.image_hash or ""].model_copy(
            update={"input_tokens": 40, "output_tokens": 60, "model": profile.model}
        )
        for case in selected
    )


def test_simulated_visual_and_extraction_calls_share_ordered_budget_accounting(
    db: Database,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An injected visual backend records observed usage before each replay extraction."""
    results = _visual_pair(tmp_path)

    @contextmanager
    def scripted(_profile: object) -> Iterator[FakeTranscriber]:
        yield FakeTranscriber(results)

    monkeypatch.setattr("datakeel.cli.kg_image_evaluation.create_transcriber", scripted)
    report = evaluate(
        db,
        ImageEvaluationRequest(
            cases=tmp_path, transcription_profile=str(tmp_path / "profile.yaml")
        ),
    )
    traces = list_traces(db, report.id)
    assert [trace.call_type for trace in traces] == [
        "transcription",
        "extraction",
        "transcription",
        "extraction",
    ]
    assert [trace.turn for trace in traces] == [1, 2, 3, 4]
    assert [trace.accounted_tokens for trace in traces if trace.call_type == "transcription"] == [
        100,
        100,
    ]
    assert report.input_tokens == 80
    assert report.output_tokens == 120
    assert report.cost_usd is None
