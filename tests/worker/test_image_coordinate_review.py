# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Keep text extraction usable while rejecting and persisting unreliable visual geometry."""

from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING

from datakeel.core.kg_queries import KGQuery
from datakeel.core.transcription_models import TranscriptionProfile
from datakeel.storage.kg_queries import query_kg
from datakeel.storage.transcription_store import cached_transcription
from datakeel.transcription.adapters import FakeTranscriber
from datakeel.transcription.auto_adapter import AutoTranscriber
from datakeel.transcription.cache import cache_key
from tests.kg.integration_helpers import execute_graph, install_adapter, pair_result
from tests.worker.image_helpers import image_dataset, prepare_image, transcript, use_profile

if TYPE_CHECKING:
    from collections.abc import Generator
    from pathlib import Path

    import pytest

    from datakeel.storage.database import Database


def _install_auto(monkeypatch: pytest.MonkeyPatch, scripted: FakeTranscriber) -> list[None]:
    constructions: list[None] = []

    @contextmanager
    def factory(selected: TranscriptionProfile, **_kwargs: object) -> Generator[AutoTranscriber]:
        constructions.append(None)
        yield AutoTranscriber(
            scripted,
            selected.auto_routing,
            coordinate_min_median_iou=selected.coordinate_min_median_iou,
        )

    monkeypatch.setattr("datakeel.worker.kg_transcription.create_transcriber", factory)
    return constructions


def test_auto_unreliable_coordinates_complete_cache_and_leave_relation_unlocated(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failed coordinate check preserves text/cache/review issues without drawing wrong frames."""
    dataset = image_dataset(db, tmp_path)
    profile = use_profile(
        monkeypatch,
        TranscriptionProfile(id="fixture", backend="fake", mode="auto", model="scripted"),
    )
    reference = transcript()
    reference = reference.model_copy(
        update={"lines": (reference.lines[0].model_copy(update={"confidence": 0.5}),)}
    )
    visual = transcript().model_copy(
        update={
            "mode": "vlm",
            "ignored_field_count": 2,
            "lines": (reference.lines[0].model_copy(update={"bbox": (10, 60, 180, 80)}),),
        }
    )
    scripted = FakeTranscriber((reference, visual))
    constructions = _install_auto(monkeypatch, scripted)
    extractor = install_adapter(monkeypatch, (pair_result(),))
    first = execute_graph(db, prepare_image(db, dataset))
    assert first.status == "completed"
    assert first.report.transcription_failed == 0
    assert first.report.transcriptions[0].quality_issues == ("coordinates_unreliable",)
    assert first.report.transcriptions[0].ignored_field_count == 2
    assert first.report.unlocated_relations == 1
    cached = cached_transcription(db, cache_key(dataset.files[0].sha256, profile, mode="auto"))
    assert cached is not None
    assert cached.text == visual.text
    assert cached.lines == ()
    assert cached.quality_issues == ("coordinates_unreliable",)
    assert cached.ignored_field_count == 2
    relation = query_kg(db, KGQuery()).relations[0]
    assert relation.image_located is False
    assert relation.assertion.verification_detail is not None
    assert {issue.code for issue in relation.assertion.verification_detail.issues} == {
        "image_unlocated"
    }
    second = execute_graph(db, prepare_image(db, dataset))
    assert second.status == "completed"
    assert second.report.transcriptions[0].cached
    assert second.report.transcriptions[0].quality_issues == ("coordinates_unreliable",)
    assert second.report.transcriptions[0].ignored_field_count == 2
    assert extractor.calls == len(constructions) == 1
