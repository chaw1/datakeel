# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Caption spans identify NFC code points and fold aliases into canonical concepts."""

import json
from pathlib import Path

from datakeel.core.evidence_inputs import sample_sidecars
from datakeel.core.evidence_models import EvidenceValue, TextSpan
from datakeel.core.models import FileItem
from tests.operators.evidence.helpers import drafts, run_node


def test_caption_when_unicode_and_aliases_present_anchors_normalized_spans(
    sample: FileItem, tmp_path: Path
) -> None:
    """Verify NFC offsets, Chinese aliases, case folding, and scene mentions."""
    caption = sample_sidecars(sample).caption
    assert caption is not None
    Path(caption.path).write_text(
        "cafe\u0301 行人 and PEDESTRIAN with cars at nighttime", encoding="utf-8"
    )
    result = run_node("caption_mentions", sample, tmp_path)
    person = next(
        draft
        for draft in drafts(result)
        if draft.object == EvidenceValue(concept="person", value="present")
    )
    text = result.metadata["caption_text"]
    assert text.startswith("café ")
    spans = [item.selector for item in person.anchors]
    assert all(isinstance(span, TextSpan) for span in spans)
    assert [text[span.start : span.end] for span in spans if isinstance(span, TextSpan)] == [
        "行人",
        "PEDESTRIAN",
    ]
    assert set(result.metadata["caption_mentions"]) == {"person", "car", "night"}
    assert all(draft.predicate == "mentions" for draft in drafts(result))


def test_caption_when_json_field_supplied_parses_only_caption(
    sample: FileItem, tmp_path: Path
) -> None:
    """Verify a shared COCO-style JSON document can also supply a caption field."""
    sidecars = sample_sidecars(sample)
    assert sidecars.caption is not None
    Path(sidecars.caption.path).write_text(
        json.dumps({"caption": "rain indoors", "annotations": []})
    )
    caption = sidecars.caption.model_copy(update={"filename": "caption.json"})
    altered = sample.model_copy(
        update={
            "metadata": {
                **sample.metadata,
                "evidence_sample": sidecars.model_copy(update={"caption": caption}).model_dump(),
            }
        }
    )
    result = run_node("caption_mentions", altered, tmp_path)
    assert result.metadata["caption_mentions"] == ["rain", "indoor"]


def test_caption_when_missing_returns_unknown_without_failure(
    sample: FileItem, tmp_path: Path
) -> None:
    """Verify absence of a sidecar is missing evidence, not evidence of absence."""
    sidecars = sample_sidecars(sample).model_copy(update={"caption": None})
    altered = sample.model_copy(
        update={"metadata": {**sample.metadata, "evidence_sample": sidecars.model_dump()}}
    )
    result = run_node("caption_mentions", altered, tmp_path)
    assert not result.metadata["caption_available"]
    assert not result.metadata["evidence_failed"]
    assert all(
        isinstance(draft.object, EvidenceValue) and draft.object.value == "unknown"
        for draft in drafts(result)
    )


def test_caption_when_decode_fails_reports_unknown_and_failure(
    sample: FileItem, tmp_path: Path
) -> None:
    """Verify unreadable caption bytes do not become negative claims."""
    sidecar = sample_sidecars(sample).caption
    assert sidecar is not None
    Path(sidecar.path).write_bytes(b"\xff")
    result = run_node("caption_mentions", sample, tmp_path)
    assert result.metadata["evidence_failed"]
    assert result.metadata["caption_mentions"] == []


def test_caption_when_word_is_substring_does_not_invent_match(
    sample: FileItem, tmp_path: Path
) -> None:
    """Verify ASCII aliases respect word boundaries."""
    caption = sample_sidecars(sample).caption
    assert caption is not None
    Path(caption.path).write_text("scar and personal notes", encoding="utf-8")
    assert run_node("caption_mentions", sample, tmp_path).metadata["caption_mentions"] == []
