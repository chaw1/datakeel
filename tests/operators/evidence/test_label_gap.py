# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Gap decisions depend on observed canonical concepts and available modalities."""

from pathlib import Path

from datakeel.core.evidence_inputs import sample_sidecars
from datakeel.core.evidence_models import EvidenceValue
from datakeel.core.models import FileItem
from tests.operators.evidence.helpers import drafts, paired_file, run_node


def _extract(sample: FileItem, tmp_path: Path) -> FileItem:
    for node in ("caption_mentions", "annotation_labels", "label_gap"):
        sample = run_node(node, sample, tmp_path)
    return sample


def test_label_gap_when_mentioned_and_missing_from_supplied_labels_is_present(
    tmp_path: Path, sample: FileItem
) -> None:
    """Verify the deliberately conflicting sample yields a person gap only."""
    result = _extract(paired_file(tmp_path, "val/scene-0016/image.png"), tmp_path)
    assert [draft.object for draft in drafts(result)] == [
        EvidenceValue(concept="person", value="present")
    ]


def test_label_gap_when_both_sides_agree_emits_nothing(sample: FileItem, tmp_path: Path) -> None:
    """Verify correctly annotated mentions are not turned into negative assertions."""
    assert drafts(_extract(sample, tmp_path)) == []


def test_label_gap_when_annotations_missing_is_unknown(sample: FileItem, tmp_path: Path) -> None:
    """Verify the no-sidecar branch cannot be mistaken for measured absence."""
    sidecars = sample_sidecars(sample).model_copy(update={"annotation": None})
    altered = sample.model_copy(
        update={"metadata": {**sample.metadata, "evidence_sample": sidecars.model_dump()}}
    )
    result = _extract(altered, tmp_path)
    assert [draft.object for draft in drafts(result)] == [
        EvidenceValue(concept="person", value="unknown"),
        EvidenceValue(concept="car", value="unknown"),
    ]


def test_label_gap_when_caption_missing_is_unknown(sample: FileItem, tmp_path: Path) -> None:
    """Verify both required modalities use the same missing-evidence rule."""
    sidecars = sample_sidecars(sample).model_copy(update={"caption": None})
    altered = sample.model_copy(
        update={"metadata": {**sample.metadata, "evidence_sample": sidecars.model_dump()}}
    )
    assert all(
        isinstance(draft.object, EvidenceValue) and draft.object.value == "unknown"
        for draft in drafts(_extract(altered, tmp_path))
    )
