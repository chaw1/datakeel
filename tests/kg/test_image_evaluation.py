# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Frozen multimodal reconciliation, external cases and actual assertion scoring."""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

import pytest
import yaml

from datakeel.core.errors import ValidationError
from datakeel.core.kg_errors import KGExtractionError
from datakeel.core.kg_eval_models import ScoredRecord, ScoredRelation
from datakeel.core.kg_models import ExtractionResult, RawExtraction, Recording, TextBlock
from datakeel.core.transcription_models import TranscriptionRecording
from datakeel.kg.cache import build_cache_key
from datakeel.kg.extractors import FakeExtractor, ReplayExtractor
from datakeel.kg.loader import contracts_path, get_profile, get_schema, load_contract
from datakeel.kg.prompt import IMAGE_DIRECTION_RULE, extraction_prompt
from datakeel.kg_eval.image_loader import image_path, load_image_cases
from datakeel.kg_eval.image_metrics import image_scores, region_iou, union_area
from datakeel.kg_eval.image_service import evaluate_image
from datakeel.transcription.adapters import FakeTranscriber, ReplayTranscriber
from datakeel.transcription.loader import get_profile as get_transcription_profile

if TYPE_CHECKING:
    from pathlib import Path


def external_case(tmp_path: Path, index: int = 12) -> Path:
    """Copy one licensed synthetic image and its frozen independent labels."""
    suite, _, directory = load_image_cases(get_schema())
    case = suite.cases[index]
    target = tmp_path / case.image
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(image_path(directory, case.image).read_bytes())
    (tmp_path / "cases.yaml").write_text(
        yaml.safe_dump({"id": "holdout", "cases": [case.model_dump(mode="json")]})
    )
    return tmp_path


def archive(name: str) -> TranscriptionRecording:
    """Load a portable original recording with its OCR geometry intact."""
    return load_contract(contracts_path() / "recordings" / f"{name}.yaml", TranscriptionRecording)


@pytest.mark.parametrize(
    ("profile", "transcription", "f1", "boxes", "traps"),
    [
        (
            "replay-image-rapidocr-qwen",
            "replay-image-ocr",
            (0.868, 0.868, 0.608),
            (0.869, 0.960, 0.356),
            (2, 2, 8),
        ),
        (
            "replay-image-flash",
            "replay-image-demo",
            (0.978, 0.978, 0.927),
            (0.882, 0.955, 0.671),
            (0, 0, 1),
        ),
        ("replay-image-qwen", "replay-image-demo", (0.0, 0.0, 0.711), (0.0, 0.0, 0.519), (0, 0, 6)),
    ],
)
def test_image_recordings_reconcile_frozen_reference_counts(
    profile: str,
    transcription: str,
    f1: tuple[float, ...],
    boxes: tuple[float, ...],
    traps: tuple[int, ...],
) -> None:
    """All three mandated routes reproduce strict F1, traps and OCR envelope localisation."""
    extraction = get_profile(profile)
    selected = get_transcription_profile(transcription)
    assert extraction.recording
    assert selected.recording
    recordings = load_contract(contracts_path() / selected.recording, TranscriptionRecording)
    report = evaluate_image(
        extraction,
        get_schema(),
        ReplayExtractor.from_path(contracts_path() / extraction.recording),
        selected,
        ReplayTranscriber(recordings, selected.mode),
    )
    assert report.image_recording is not None
    groups = report.image_recording.groups[:3]
    assert tuple(group.metrics.relation_strict.f1 for group in groups) == f1
    assert tuple(group.box_hit_rate for group in groups) == boxes
    assert tuple(group.metrics.trap_hits for group in groups) == traps
    assert report.image_product is not None
    assert report.cost_usd == 0
    if profile == "replay-image-flash":
        assert {failure.case_id for failure in report.failures} == {"en08_clean", "en08_scan"}
        assert all(failure.reason == "AssertionError: " for failure in report.failures)


def test_recording_deduplication_preserves_smallest_case_and_error() -> None:
    """Identical transcript keys select the smallest case identity, including failed output."""
    suite, _, _ = load_image_cases(get_schema())
    transcripts = {record.image_hash: record for record in archive("qwen-image").records}
    recording = load_contract(contracts_path() / "recordings/image-flash.yaml", Recording)
    expected: dict[str, list[str]] = {}
    for case in suite.cases:
        transcript = transcripts[case.image_hash or ""]
        key = hashlib.sha256(transcript.text.encode()).hexdigest()
        expected.setdefault(key, []).append(case.id)
    assert len(recording.records) == 40
    for record in recording.records:
        assert isinstance(record.original, dict)
        assert record.original["pid"] == min(expected[record.text_hash])
    failure = next(record for record in recording.records if record.error)
    assert failure.original
    assert isinstance(failure.original, dict)
    assert failure.original["pid"] == "en08_clean"
    adapter = ReplayExtractor(recording)
    text = next(
        item.text
        for item in transcripts.values()
        if hashlib.sha256(item.text.encode()).hexdigest() == failure.text_hash
    )
    with pytest.raises(KGExtractionError, match="AssertionError"):
        adapter.extract(TextBlock(text=text, start=0, end=len(text)), get_schema())


def test_product_box_iou_uses_geometric_union_without_filling_gaps() -> None:
    """Two narrow regions cannot claim the empty space inside their enclosing rectangle."""
    regions = ((0.0, 0.0, 1.0, 10.0), (9.0, 0.0, 10.0, 10.0))
    assert union_area(regions) == 20
    assert region_iou(regions, (0.0, 0.0, 10.0, 10.0)) == 0.2
    assert union_area(((0, 0, 5, 5), (2, 2, 8, 8))) == 52
    assert region_iou((), (0, 0, 0, 0)) == 0


def test_missing_gold_boxes_are_excluded_and_missing_transcript_is_failed() -> None:
    """External labels may omit geometry without receiving an invented localisation failure."""
    suite, _, _ = load_image_cases(get_schema())
    case = suite.cases[0]
    relation = case.relations[0]
    case = case.model_copy(update={"relations": (relation.model_copy(update={"boxes": ()}),)})
    record = ScoredRecord(
        pid=case.id,
        relations=(
            ScoredRelation(head=relation.head, relation=relation.relation, tail=relation.tail),
        ),
    )
    scored = image_scores(
        (record,), suite.model_copy(update={"cases": (case,)}), {relation.relation}, {}
    )
    group = next(item for item in scored.groups if item.name == case.group)
    assert group.box_true_positives == 0
    assert group.transcription_failures == 1


@pytest.mark.parametrize(
    "change", ["duplicate", "type", "relation", "traversal", "hash", "missing", "box"]
)
def test_external_image_cases_validate_provenance_and_schema(tmp_path: Path, change: str) -> None:
    """Holdout manifests cannot invent vocabulary, escape their directory or change frozen bytes."""
    external_case(tmp_path)
    path = tmp_path / "cases.yaml"
    data = yaml.safe_load(path.read_text())
    case = data["cases"][0]
    if change == "duplicate":
        data["cases"].append(case)
    elif change == "type":
        case["entities"][0]["type"] = "unknown_type"
    elif change == "relation":
        case["relations"][0]["relation"] = "unknown_relation"
    elif change == "traversal":
        case["image"] = "../outside.png"
    elif change == "hash":
        case["image_hash"] = "0" * 64
    elif change == "box":
        case["relations"][0]["boxes"] = [[0, 0, 99999, 99999]]
    else:
        case["image"] = "missing.png"
    path.write_text(yaml.safe_dump(data))
    with pytest.raises(ValidationError):
        load_image_cases(get_schema(), tmp_path)


def test_image_quality_failure_is_visible_and_prevents_extraction(tmp_path: Path) -> None:
    """Rejected transcription contributes zero product predictions and one explicit failure."""
    external_case(tmp_path)
    suite, _, _ = load_image_cases(get_schema(), tmp_path)
    original = next(
        record
        for record in archive("qwen-image").records
        if record.image_hash == suite.cases[0].image_hash
    )
    scripted = original.model_copy(update={"finish_reason": "length"})
    extraction = FakeExtractor()
    report = evaluate_image(
        get_profile("fake"),
        get_schema(),
        extraction,
        get_transcription_profile("fake"),
        FakeTranscriber((scripted,)),
        tmp_path,
    )
    assert extraction.calls == 0
    assert report.failures[0].reason == "transcription:truncated"
    assert report.product.all.relation_strict.tp == 0
    assert report.image_product
    assert report.image_product.groups[0].transcription_failures == 1


def test_image_evaluation_scores_database_readback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Deleting the read projection removes product predictions despite valid raw model output."""
    external_case(tmp_path)
    profile = get_profile("replay-image-flash")
    assert profile.recording
    monkeypatch.setattr("datakeel.storage.kg_image_eval_store.read_assertions", lambda _session: [])
    report = evaluate_image(
        profile,
        get_schema(),
        ReplayExtractor.from_path(contracts_path() / profile.recording),
        get_transcription_profile("replay-image-demo"),
        ReplayTranscriber(archive("qwen-image"), "vlm"),
        tmp_path,
    )
    assert report.recording.all.relation_strict.tp > 0
    assert report.product.all.relation_strict.tp == 0


def test_image_prompt_version_changes_text_and_cache_identity() -> None:
    """Directional conventions affect only explicitly versioned image extraction profiles."""
    from datakeel.core.evidence_models import ExtractorRef  # noqa: PLC0415

    schema = get_schema()
    block = TextBlock(text="A --> B", start=0, end=7)
    ordinary = get_profile("fake")
    image = ordinary.model_copy(update={"prompt_version": "image-kg-v1"})
    assert IMAGE_DIRECTION_RULE not in extraction_prompt(block, schema)
    assert IMAGE_DIRECTION_RULE in extraction_prompt(block, schema, image.prompt_version)
    ref = ExtractorRef(id="evidence.kg", version="1")
    assert build_cache_key(block, schema, ordinary, ref) != build_cache_key(
        block, schema, image, ref
    )


@pytest.mark.parametrize("field", ["width", "transcription_width"])
def test_image_evaluation_rejects_coordinate_system_mismatch(tmp_path: Path, field: str) -> None:
    """Manifest and returned OCR geometry must match the corrected image pixels."""
    external_case(tmp_path)
    suite, _, _ = load_image_cases(get_schema(), tmp_path)
    original = next(
        record
        for record in archive("qwen-image").records
        if record.image_hash == suite.cases[0].image_hash
    )
    if field == "width":
        path = tmp_path / "cases.yaml"
        data = yaml.safe_load(path.read_text())
        data["cases"][0]["width"] += 1
        path.write_text(yaml.safe_dump(data))
    else:
        original = original.model_copy(update={"width": original.width + 1})
    with pytest.raises(ValidationError, match="pixels"):
        evaluate_image(
            get_profile("fake"),
            get_schema(),
            FakeExtractor((ExtractionResult(output=RawExtraction()),)),
            get_transcription_profile("fake"),
            FakeTranscriber((original,)),
            tmp_path,
        )


def test_external_holdout_can_omit_gold_text_dimensions_and_boxes(tmp_path: Path) -> None:
    """Only labelled entities and triples are required beyond each image reference."""
    external_case(tmp_path)
    path = tmp_path / "cases.yaml"
    data = yaml.safe_load(path.read_text())
    case = data["cases"][0]
    for field in ("text", "width", "height", "image_hash"):
        case.pop(field)
    for relation in case["relations"]:
        relation.pop("boxes")
    path.write_text(yaml.safe_dump(data))
    profile = get_profile("replay-image-flash")
    assert profile.recording
    report = evaluate_image(
        profile,
        get_schema(),
        ReplayExtractor.from_path(contracts_path() / profile.recording),
        get_transcription_profile("replay-image-demo"),
        ReplayTranscriber(archive("qwen-image"), "vlm"),
        tmp_path,
    )
    assert report.product.all.relation_strict.tp > 0
    assert report.image_product
    assert all(group.box_true_positives == 0 for group in report.image_product.groups)


def test_nonreplay_output_cannot_be_replaced_by_attached_recording(tmp_path: Path) -> None:
    """Live and fake adapters are scored by their observations even if a file field exists."""
    external_case(tmp_path)
    profile = get_profile("fake").model_copy(update={"recording": "recordings/image-flash.yaml"})
    report = evaluate_image(
        profile,
        get_schema(),
        FakeExtractor(),
        get_transcription_profile("replay-image-demo"),
        ReplayTranscriber(archive("qwen-image"), "vlm"),
        tmp_path,
    )
    assert report.recording.all.relation_strict.tp == 0
