# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Image evaluation isolates real image-local failures and normalizes recording lookup text."""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

import pytest
import yaml

from datakeel.core.kg_eval_models import ScoredRecord, ScoredRelation
from datakeel.core.kg_models import RawExtraction, Recording, RecordingRecord
from datakeel.kg.extractors import FakeExtractor, ReplayExtractor
from datakeel.kg.loader import contracts_path, get_profile, get_schema
from datakeel.kg_eval.image_loader import image_path, load_image_cases
from datakeel.kg_eval.image_service import evaluate_image
from datakeel.transcription.adapters import FakeTranscriber, ReplayTranscriber
from datakeel.transcription.loader import get_profile as transcription_profile
from tests.kg.test_image_evaluation import archive, external_case

if TYPE_CHECKING:
    from pathlib import Path

    from datakeel.core.transcription_models import TranscriptionRecording


def _cases(directory: Path) -> TranscriptionRecording:
    suite, _, source = load_image_cases(get_schema())
    cases = suite.cases[:2]
    for case in cases:
        path = directory / case.image
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(image_path(source, case.image).read_bytes())
    (directory / "cases.yaml").write_text(
        yaml.safe_dump(
            {
                "id": "failure-continuation",
                "cases": [case.model_dump(mode="json") for case in cases],
            }
        )
    )
    recordings = archive("qwen-image")
    hashes = {case.image_hash for case in cases}
    return recordings.model_copy(
        update={
            "records": tuple(record for record in recordings.records if record.image_hash in hashes)
        }
    )


@pytest.mark.parametrize("failure", ["recording_missing", "mode_mismatch", "image_decode_error"])
def test_real_image_failure_does_not_stop_remaining_evaluation_cases(
    tmp_path: Path, failure: str
) -> None:
    """Missing recordings, mode conflicts and undecodable bytes leave the next image runnable."""
    recordings = _cases(tmp_path)
    data = yaml.safe_load((tmp_path / "cases.yaml").read_text())
    first = data["cases"][0]
    if failure == "image_decode_error":
        (tmp_path / first["image"]).write_bytes(b"invalid generated image")
        first["image_hash"] = None
        (tmp_path / "cases.yaml").write_text(yaml.safe_dump(data))
    else:
        recordings = recordings.model_copy(
            update={
                "records": tuple(
                    record.model_copy(update={"mode": "ocr", "backend": "ocr"})
                    if record.image_hash == first["image_hash"]
                    else record
                    for record in recordings.records
                    if failure != "recording_missing" or record.image_hash != first["image_hash"]
                )
            }
        )
    profile = get_profile("replay-image-flash")
    report = evaluate_image(
        profile,
        get_schema(),
        ReplayExtractor.from_path(contracts_path() / (profile.recording or "")),
        transcription_profile("replay-image-demo"),
        ReplayTranscriber(recordings, "vlm"),
        tmp_path,
    )
    assert len(report.failures) == 1
    assert report.failures[0].reason == f"transcription:{failure}"
    assert report.failures[0].case_id == first["id"]
    assert report.product.all.relation_strict.tp > 0


def test_recorded_transcript_lookup_normalizes_nfc_before_hashing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Decomposed output finds the same recorded original as the NFC extraction block."""
    external_case(tmp_path)
    suite, _, _ = load_image_cases(get_schema(), tmp_path)
    case = suite.cases[0]
    observed = next(
        record for record in archive("qwen-image").records if record.image_hash == case.image_hash
    )
    relation = case.relations[0]
    original = ScoredRecord(
        pid=case.id,
        relations=(
            ScoredRelation(
                head=relation.head,
                relation=relation.relation,
                tail=relation.tail,
                evidence="Café",
            ),
        ),
    )
    recording = Recording(
        model="fixture",
        recorded_at="2026-10-25",
        prompt_version="image-kg-v1",
        source="Generated NFC fixture",
        records=(
            RecordingRecord(
                text_hash=hashlib.sha256("Café".encode()).hexdigest(),
                output=RawExtraction(),
                original=original.model_dump(mode="json"),
            ),
        ),
    )
    monkeypatch.setattr("datakeel.kg_eval.image_service.load_recording", lambda _path: recording)
    report = evaluate_image(
        get_profile("replay-image-flash"),
        get_schema(),
        FakeExtractor(),
        transcription_profile("fake"),
        FakeTranscriber((observed.model_copy(update={"text": "Cafe\u0301"}),)),
        tmp_path,
    )
    assert report.recording.all.pred_relations == 1
    assert report.product.all.pred_relations == 0
