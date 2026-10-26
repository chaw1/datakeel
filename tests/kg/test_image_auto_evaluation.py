# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Independent labels measure real automatic replay decisions and persisted graph predictions."""

from __future__ import annotations

import hashlib
import socket
from typing import TYPE_CHECKING

import pytest
import yaml

from datakeel.core.kg_eval_models import ScoredRecord
from datakeel.core.kg_image_eval import KGImageSuite
from datakeel.core.transcription_auto import AutoRouteDecision
from datakeel.core.transcription_models import TranscriptionMode, TranscriptionResult
from datakeel.kg.extractors import ReplayExtractor
from datakeel.kg.loader import contracts_path, get_profile, get_schema
from datakeel.kg_eval.image_auto_metrics import auto_metrics
from datakeel.kg_eval.image_execution import ImageCaseExecution
from datakeel.kg_eval.image_loader import load_image_cases
from datakeel.kg_eval.image_service import evaluate_image
from datakeel.transcription.factory import create_transcriber
from datakeel.transcription.loader import get_profile as transcription_profile
from scripts import generate_auto_image_cases

if TYPE_CHECKING:
    from pathlib import Path

    from datakeel.core.kg_eval_models import KGEvalReport


def _evaluate(mode: TranscriptionMode, directory: Path | None = None) -> KGEvalReport:
    profile = get_profile("replay-image-auto")
    selected = transcription_profile("replay-image-auto").model_copy(update={"mode": mode})
    assert profile.recording
    with create_transcriber(selected) as transcriber:
        return evaluate_image(
            profile,
            get_schema(),
            ReplayExtractor.from_path(contracts_path() / profile.recording),
            selected,
            transcriber,
            directory or contracts_path() / "eval" / "image-auto",
        )


def test_auto_matches_visual_structure_and_reduces_visual_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A replay comparison includes all OCR/VLM baselines without credential reads or sockets."""

    def forbidden(*_args: object, **_kwargs: object) -> None:
        pytest.fail("Generated replay evaluation attempted network or credential access")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr("datakeel.transcription.factory.get_settings", forbidden)
    ocr, visual, automatic = (_evaluate(mode) for mode in ("ocr", "vlm", "auto"))
    assert ocr.product.all.relation_strict.f1 == 0.769
    assert automatic.product.all.relation_strict.f1 == visual.product.all.relation_strict.f1 == 1
    assert automatic.image_auto is not None
    measured = automatic.image_auto
    assert measured.route_correct == measured.labelled_cases == measured.cases == 6
    assert measured.route_accuracy == measured.extraction_f1 == 1
    assert measured.vlm_images == 3
    assert measured.vlm_ratio == 0.5
    assert measured.external_images == measured.external_ratio == 0
    assert all(not route.external for route in measured.routes)
    assert all(
        route.route == "ocr" for route in measured.routes if route.case_id.startswith("text")
    )
    assert automatic.image_product is not None
    assert visual.image_product is not None
    assert automatic.image_product.groups[2].metrics.relation_strict.f1 == 1
    assert visual.image_product.groups[2].metrics.relation_strict.f1 == 1
    assert ocr.product.all.trap_hits == 2
    assert automatic.product.all.trap_hits == 0
    assert {reason for route in measured.routes for reason in route.reasons} == {
        "clean_text",
        "structure_diagram",
        "struck_or_greyed_rows",
    }


def test_expected_route_changes_scores_without_changing_actual_routing(tmp_path: Path) -> None:
    """Gold route labels cannot instruct the automatic transcriber which backend to select."""
    suite, _, directory = load_image_cases(get_schema(), contracts_path() / "eval" / "image-auto")
    for case in suite.cases:
        target = tmp_path / case.image
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((directory / case.image).read_bytes())
    inverted = suite.model_copy(
        update={
            "cases": tuple(
                case.model_copy(
                    update={"expected_route": "vlm" if case.expected_route == "ocr" else "ocr"}
                )
                for case in suite.cases
            )
        }
    )
    (tmp_path / "cases.yaml").write_text(yaml.safe_dump(inverted.model_dump(mode="json")))
    report = _evaluate("auto", tmp_path)
    assert report.image_auto is not None
    assert report.image_auto.route_accuracy == 0
    assert report.image_auto.vlm_ratio == 0.5
    assert report.image_auto.extraction_f1 == 1


def test_generator_reproduces_all_six_images_and_both_replay_archives(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """All new image pixels and scripted observations are reproducible from checked-in code."""
    monkeypatch.setattr(generate_auto_image_cases, "ROOT", tmp_path)
    (tmp_path / "recordings").mkdir()
    generate_auto_image_cases.main()
    generated = tmp_path / "eval" / "image-auto"
    suite, _, _ = load_image_cases(get_schema(), generated)
    assert len(suite.cases) == 6
    assert sum(case.expected_route == "vlm" for case in suite.cases) == 3
    for case in suite.cases:
        original = contracts_path() / "eval" / "image-auto" / case.image
        assert hashlib.sha256(original.read_bytes()).hexdigest() == case.image_hash
        assert (generated / case.image).read_bytes() == original.read_bytes()
    for name in ("auto-transcription.yaml", "auto-extraction.yaml"):
        assert (tmp_path / "recordings" / name).read_bytes() == (
            contracts_path() / "recordings" / name
        ).read_bytes()


def _execution(mode: TranscriptionMode, *, decision: bool = False) -> ImageCaseExecution:
    record = ScoredRecord(pid="connector")
    return ImageCaseExecution(
        raw=record,
        product=record,
        blocked=(),
        failures=(),
        transcript=TranscriptionResult(
            text="",
            width=1,
            height=1,
            backend="fake",
            mode=mode,
            auto_decision=AutoRouteDecision(route="vlm", reasons=("ocr_failed",))
            if decision
            else None,
        ),
    )


@pytest.mark.parametrize("mode", ["ocr", "vlm", "auto"])
def test_route_metrics_distinguish_remote_transfer_local_route_and_failure(
    mode: TranscriptionMode,
) -> None:
    """Unresolved failures count as incorrect and only remote visual routes count as transfers."""
    suite, _, _ = load_image_cases(get_schema(), contracts_path() / "eval" / "image-auto")
    suite = suite.model_copy(update={"cases": (suite.cases[3],)})
    remote = transcription_profile("replay-image-auto").model_copy(
        update={
            "backend": "vlm",
            "base_url": "https://vision.example/v1",
        }
    )
    measured = auto_metrics(suite, (_execution(mode),), remote, 0.25)
    assert measured is not None
    assert measured.external_images == measured.vlm_images == int(mode == "vlm")
    assert measured.route_accuracy == int(mode == "vlm")
    assert measured.routes[0].route == (mode if mode != "auto" else None)
    assert measured.extraction_f1 == 0.25


def test_route_metrics_use_decision_and_ignore_unlabelled_cases() -> None:
    """The resolved auto decision wins and unlabelled images stay outside accuracy denominators."""
    suite, _, _ = load_image_cases(get_schema(), contracts_path() / "eval" / "image-auto")
    selected = suite.cases[3].model_copy(update={"expected_route": None})
    labelled = suite.cases[0].model_copy(update={"id": "text-staff", "expected_route": "vlm"})
    suite = suite.model_copy(update={"cases": (labelled, selected)})
    measured = auto_metrics(
        suite, (_execution("auto", decision=True),), transcription_profile("replay-image-auto"), 0
    )
    assert measured is not None
    assert measured.labelled_cases == 1
    assert measured.route_accuracy == 0
    assert measured.routes[0].route is None
    assert measured.routes[1].route == "vlm"
    assert measured.routes[1].reasons == ("ocr_failed",)
    empty = auto_metrics(suite, (), transcription_profile("replay-image-auto"), 0)
    assert empty is not None
    assert empty.external_ratio == empty.vlm_ratio == 0
    assert empty.labelled_cases == 1
    assert empty.route_accuracy == 0
    legacy = KGImageSuite(id="legacy", cases=(selected,))
    assert auto_metrics(legacy, (), transcription_profile("replay-image-auto"), 0) is None
