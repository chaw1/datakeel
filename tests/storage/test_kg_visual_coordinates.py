# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Publish recorded visual rectangles through the real image action and worker boundary."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
import yaml

from datakeel.core.evidence_models import ImageRegion
from datakeel.core.transcription_models import (
    TranscriptionProfile,
    TranscriptionRecord,
    TranscriptionRecording,
)
from datakeel.storage.evidence_projection import rebuild_evidence
from datakeel.storage.evidence_store import list_assertions
from tests.kg.integration_helpers import execute_graph, install_adapter, pair_result
from tests.worker.image_helpers import image_dataset, prepare_image, use_profile

if TYPE_CHECKING:
    from pathlib import Path

    from datakeel.storage.database import Database


@pytest.mark.parametrize("bbox", ["[12,18,175,45]", "[-1,0,175,45]", "null"])
def test_visual_coordinate_record_when_extracted_publishes_only_valid_image_regions(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, bbox: str
) -> None:
    """Replay JSON produces real image evidence; invalid or omitted locations remain unlocated."""
    dataset = image_dataset(db, tmp_path)
    record = TranscriptionRecord(
        image_hash=dataset.files[0].sha256,
        text='{"lines":[{"text":"Acme uses Widget.","bbox":' + bbox + "}]}",
        width=200,
        height=100,
        backend="vlm",
        mode="vlm",
    )
    archive = TranscriptionRecording(
        model="fixture",
        recorded_at="2026-10-26",
        prompt_version="image-transcription-v2",
        source="generated fixture",
        records=(record,),
    )
    path = tmp_path / "visual.yaml"
    path.write_text(yaml.safe_dump(archive.model_dump(mode="json")), encoding="utf-8")
    use_profile(
        monkeypatch,
        TranscriptionProfile(
            id="fixture",
            backend="replay",
            mode="vlm",
            model="fixture",
            recording=str(path),
            prompt_version="image-transcription-v2",
        ),
    )
    install_adapter(monkeypatch, (pair_result(),))
    run = execute_graph(db, prepare_image(db, dataset))
    relation = next(item for item in list_assertions(db) if item.predicate == "kg.uses")
    regions = [
        anchor.selector for anchor in relation.anchors if isinstance(anchor.selector, ImageRegion)
    ]
    assert run.status == "completed"
    assert bool(regions) == (bbox == "[12,18,175,45]")
    assert all(region.bbox == (12, 18, 175, 45) for region in regions)
    assert run.report.located_relations == bool(regions)
    if not regions:
        assert relation.verification_detail is not None
        assert "image_unlocated" in {issue.code for issue in relation.verification_detail.issues}
    assert rebuild_evidence(db).matches
