# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Independent WebVTT parsing, native round trips and eager segment format protection."""

import hashlib
import json
from collections.abc import Callable
from pathlib import Path

import pytest

from datakeel.core.annotation_models import AnnotationRecord, AnnotationSegment
from datakeel.core.errors import ValidationError
from datakeel.core.models import FileItem
from datakeel.core.training_export_models import (
    TrainingExport,
    TrainingExportItem,
    TrainingFormat,
)
from datakeel.training.export import write_training_export
from datakeel.training.export_segments import webvtt_text
from datakeel.training.native import import_annotations_jsonl


def _reject(call: Callable[[], object], match: str) -> None:
    message = None
    try:
        call()
    except ValidationError as error:
        message = str(error)
    assert message is not None, "Expected segment export validation to reject the operation"
    assert match in message


def _item(tmp_path: Path, *, empty: bool = False) -> TrainingExportItem:
    source = tmp_path / ("empty.wav" if empty else "speech.wav")
    content = b"RIFF-local-fixture" + bytes([empty])
    source.write_bytes(content)
    file = FileItem(
        id="empty" if empty else "audio",
        path=str(source),
        filename=source.name,
        modality="audio",
        sha256=hashlib.sha256(content).hexdigest(),
        size=len(content),
        metadata={"media_probe": {"duration_ms": 3250, "codec": "pcm_s16le", "format": "wav"}},
    )
    segments = (
        ()
        if empty
        else (
            AnnotationSegment(
                category="speech", start_ms=1000, end_ms=2000, attributes={"说明": "重叠"}
            ),
            AnnotationSegment(category="noise", start_ms=0, end_ms=1500),
            AnnotationSegment(category="speech", start_ms=1000, end_ms=2000),
        )
    )
    return TrainingExportItem(
        file=file,
        split="train",
        annotation=AnnotationRecord(
            sample_id=file.id,
            annotator_id="ann",
            labels=("reviewed",),
            segments=segments,
            media_duration_ms=3250,
            attributes={"record": True},
        ),
    )


def _export(tmp_path: Path, format_name: TrainingFormat) -> TrainingExport:
    return TrainingExport(
        dataset_id="d",
        version_id="v",
        split_set_id="s",
        seed=1,
        format=format_name,
        items=(_item(tmp_path), _item(tmp_path, empty=True)),
    )


def _write(export: TrainingExport, directory: Path) -> Path:
    package = directory / "package"
    write_training_export(export, package, directory / "export.tar")
    return package


def _cues(text: str) -> list[tuple[str, str, str, str]]:
    lines = text.splitlines()
    result = []
    for index, line in enumerate(lines):
        if " --> " not in line:
            continue
        start, end = line.split(" --> ")
        result.append((lines[index - 1], start, end, lines[index + 1]))
    return result


def test_native_jsonl_roundtrip_preserves_order_attributes_empty_and_duration(
    tmp_path: Path,
) -> None:
    """Native rows retain record order, Chinese attributes, source duration and reviewed empty."""
    export = _export(tmp_path, "annotations_jsonl")
    package = _write(export, tmp_path / "native")
    rows = (package / "annotations.jsonl").read_text(encoding="utf-8").splitlines()
    assert import_annotations_jsonl("\n".join(rows)) == tuple(
        item.annotation for item in export.items
    )
    first = json.loads(rows[0])
    assert [segment["start_ms"] for segment in first["segments"]] == [1000, 0, 1000]
    assert first["segments"][0]["attributes"] == {"说明": "重叠"}
    assert json.loads(rows[1])["segments"] == []
    manifest = json.loads((package / "MANIFEST.json").read_text())
    assert manifest["annotation_count"] == 5


def test_webvtt_has_stable_sorted_cues_notes_media_and_legal_empty_file(tmp_path: Path) -> None:
    """An independent cue parser sees stable overlap order, milliseconds, notes and empty output."""
    export = _export(tmp_path, "webvtt")
    package = _write(export, tmp_path / "vtt")
    files = sorted((package / "annotations/train").glob("*.vtt"))
    assert len(files) == 2
    texts = [path.read_text(encoding="utf-8") for path in files]
    populated = next(text for text in texts if "segment-1" in text)
    empty = next(text for text in texts if "segment-1" not in text)
    assert _cues(populated) == [
        ("segment-2", "00:00:00.000", "00:00:01.500", "noise"),
        ("segment-1", "00:00:01.000", "00:00:02.000", "speech"),
        ("segment-3", "00:00:01.000", "00:00:02.000", "speech"),
    ]
    assert "NOTE sample_id=audio media_duration_ms=3250" in populated
    assert empty.startswith("WEBVTT\n\nNOTE sample_id=empty media_duration_ms=3250")
    assert _cues(empty) == []
    assert len(list((package / "media/train").glob("*.wav"))) == 2


def test_webvtt_and_archives_are_byte_stable(tmp_path: Path) -> None:
    """Repeated exports produce identical manifest and archive bytes."""
    export = _export(tmp_path, "webvtt")
    first = _write(export, tmp_path / "first")
    second = _write(export, tmp_path / "second")
    assert (first / "MANIFEST.json").read_bytes() == (second / "MANIFEST.json").read_bytes()
    assert (first.parent / "export.tar").read_bytes() == (second.parent / "export.tar").read_bytes()


def test_webvtt_rejects_unreviewed_instead_of_emitting_negative(tmp_path: Path) -> None:
    """An unreviewed record never becomes a legal but misleading empty caption file."""
    item = _item(tmp_path)
    annotation = item.annotation.model_copy(update={"segments": None})
    _reject(lambda: webvtt_text(item.model_copy(update={"annotation": annotation})), "unreviewed")


@pytest.mark.parametrize(
    "format_name", ["coco", "yolo", "imagefolder", "hf_imagefolder", "text_jsonl"]
)
def test_every_lossy_format_rejects_segments_before_writing(
    tmp_path: Path, format_name: TrainingFormat
) -> None:
    """COCO, detection, image and text formats fail before creating a partial package."""
    with pytest.raises(ValidationError, match="webvtt or annotations_jsonl"):
        _write(_export(tmp_path, format_name), tmp_path / format_name)
    assert not (tmp_path / format_name / "package").exists()
