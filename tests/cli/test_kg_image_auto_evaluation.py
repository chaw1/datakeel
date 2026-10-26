# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""The public evaluation command selects automatic transcription and stores routing scores."""

from __future__ import annotations

import argparse
from typing import TYPE_CHECKING

import pytest
from pydantic import ValidationError as ModelValidationError

from datakeel.cli import _evaluation_command
from datakeel.cli.kg_evaluation import register_parser
from datakeel.cli.kg_image_evaluation import evaluate
from datakeel.core.kg_image_request import ImageEvaluationRequest
from datakeel.storage.kg_evaluations import get_evaluation, list_evaluations

if TYPE_CHECKING:
    from datakeel.core.transcription_models import TranscriptionMode
    from datakeel.storage.database import Database


@pytest.mark.parametrize(("mode", "ratio"), [("auto", 0.5), ("ocr", 0), ("vlm", 1)])
def test_cli_transcription_mode_overrides_profile_and_persists_route_metrics(
    db: Database,
    capsys: pytest.CaptureFixture[str],
    mode: str,
    ratio: float,
) -> None:
    """A CLI mode selector keeps the default replay suite intact and supports all three modes."""
    parser = argparse.ArgumentParser()
    register_parser(parser.add_subparsers(dest="command"))
    args = parser.parse_args(
        [
            "eval-kg",
            "--suite",
            "image",
            "--profile",
            "replay-image-auto",
            "--transcription-profile",
            "replay-image-auto",
            "--transcription-mode",
            mode,
        ]
    )
    _evaluation_command(db, args)
    report = list_evaluations(db)[0]
    assert report.image_auto is not None
    assert report.image_auto.vlm_ratio == ratio
    assert get_evaluation(db, report.id) == report
    output = capsys.readouterr().out
    assert "Routing accuracy" in output
    assert "VLM fraction" in output
    assert "External fraction" in output


def test_cli_auto_default_mode_does_not_require_selector(db: Database) -> None:
    """A configured auto profile works with its bundled corpus without changing P10 defaults."""
    report = evaluate(
        db,
        ImageEvaluationRequest(
            profile="replay-image-auto",
            transcription_profile="replay-image-auto",
        ),
    )
    assert report.image_auto is not None
    assert report.image_auto.route_accuracy == 1


@pytest.mark.parametrize("mode", ["auto", "vlm"])
def test_cli_mode_override_revalidates_ocr_only_backend(
    db: Database, monkeypatch: pytest.MonkeyPatch, mode: TranscriptionMode
) -> None:
    """A selector cannot bypass profile validation and invent an absent visual backend."""

    def forbidden(*_args: object, **_kwargs: object) -> None:
        pytest.fail("Invalid mode override constructed a transcription backend")

    monkeypatch.setattr("datakeel.cli.kg_image_evaluation.create_transcriber", forbidden)
    with pytest.raises(ModelValidationError, match="ocr backend supports only ocr mode"):
        evaluate(
            db,
            ImageEvaluationRequest(
                profile="replay-image-auto",
                transcription_profile="rapidocr-local",
                transcription_mode=mode,
            ),
        )
    assert list_evaluations(db) == ()
