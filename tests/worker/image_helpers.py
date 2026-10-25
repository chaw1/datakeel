# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Generated images and scripted adapters for the actual image action/worker boundary."""

from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING

from PIL import Image

from datakeel.actions.service import prepare_action
from datakeel.core.models import JsonDocument
from datakeel.core.transcription_models import OCRLine, TranscriptionProfile, TranscriptionResult
from datakeel.storage.dataset_service import import_paths
from datakeel.storage.evidence_import import source_manifest
from datakeel.transcription.adapters import FakeTranscriber
from tests.kg.integration_helpers import TextDataset

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

    import pytest

    from datakeel.actions.models import ActionPlan
    from datakeel.storage.database import Database


def image_dataset(
    db: Database, directory: Path, count: int = 1, *, handwriting: bool = False
) -> TextDataset:
    """Import generated distinct pixels through the same immutable manifest as uploads."""
    paths = []
    for index in range(count):
        path = directory / f"image-{index}.png"
        Image.new("RGB", (200, 100), (index, 230, 240)).save(path)
        paths.append(path)
    dataset = import_paths(db, "Generated image graph", paths, {"handwriting": handwriting})
    version, files = source_manifest(db, dataset.id)
    return TextDataset(dataset_id=dataset.id, version_id=version, files=tuple(files))


def transcript(text: str = "Acme uses Widget.") -> TranscriptionResult:
    """Provide explicit generated text and an OCR rectangle in corrected source pixels."""
    return TranscriptionResult(
        text=text,
        lines=(OCRLine(text=text, bbox=(10, 20, 180, 40), confidence=0.95),),
        width=200,
        height=100,
        backend="fake",
        model="scripted",
        input_tokens=20,
        output_tokens=10,
    )


def install_transcriber(
    monkeypatch: pytest.MonkeyPatch, results: tuple[TranscriptionResult, ...]
) -> FakeTranscriber:
    """Replace only provider construction, preserving all product quality and lease checks."""
    adapter = FakeTranscriber(results)

    @contextmanager
    def factory(*_args: object, **_kwargs: object) -> Iterator[FakeTranscriber]:
        yield adapter

    monkeypatch.setattr("datakeel.worker.kg_transcription.create_transcriber", factory)
    return adapter


def use_profile(
    monkeypatch: pytest.MonkeyPatch, profile: TranscriptionProfile | None = None
) -> TranscriptionProfile:
    """Select a frozen generated profile without touching packaged declarations."""
    value = profile or TranscriptionProfile(id="fixture", backend="fake", model="scripted")
    monkeypatch.setattr(
        "datakeel.storage.kg_preparation.get_transcription_profile", lambda _id: value
    )
    return value


def prepare_image(db: Database, dataset: TextDataset, **params: object) -> ActionPlan:
    """Prepare the real controlled action with a generated image and offline extraction."""
    return prepare_action(
        db,
        "run_kg_extraction",
        JsonDocument.model_validate(
            {
                "dataset_id": dataset.dataset_id,
                "version_id": dataset.version_id,
                "profile_id": "fake",
                "transcription_profile_id": "fixture",
                **params,
            }
        ),
    )
