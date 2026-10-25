# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Keep text prompts, cached blocks and provenance stable inside mixed image datasets."""

from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING

from PIL import Image
from sqlalchemy import select

from datakeel.actions.kg_parameters import RunKGExtractionParams
from datakeel.core.kg_cache import KGCacheKey
from datakeel.kg.extractors import FakeExtractor
from datakeel.storage.dataset_service import import_paths
from datakeel.storage.evidence_import import source_manifest
from datakeel.storage.evidence_store import list_assertions
from datakeel.storage.kg_rows import KGCacheRow
from tests.kg.integration_helpers import TextDataset, execute_graph, pair_result
from tests.worker.image_helpers import install_transcriber, prepare_image, transcript, use_profile

if TYPE_CHECKING:
    from collections.abc import Generator
    from pathlib import Path

    import pytest

    from datakeel.core.kg_contracts import ExtractionProfile
    from datakeel.storage.database import Database


def _dataset(db: Database, directory: Path) -> TextDataset:
    text, image = directory / "source.txt", directory / "source.png"
    text.write_text("Acme uses Widget.")
    Image.new("RGB", (200, 100), "white").save(image)
    imported = import_paths(db, "Mixed document fixture", [text, image])
    version, files = source_manifest(db, imported.id)
    return TextDataset(dataset_id=imported.id, version_id=version, files=tuple(files))


def _keys(db: Database) -> dict[str, KGCacheKey]:
    with db.session() as session:
        return {
            key.prompt_version: key
            for row in session.scalars(select(KGCacheRow))
            for key in (KGCacheKey.model_validate(row.key_payload),)
        }


def test_mixed_dataset_reuses_unchanged_text_identity_and_selects_image_prompt(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Adding an image preserves the exact text cache key and only constructs an image adapter."""
    dataset = _dataset(db, tmp_path)
    text_id = next(item.id for item in dataset.files if item.filename.endswith(".txt"))
    use_profile(monkeypatch)
    install_transcriber(monkeypatch, (transcript(),))
    versions: list[str] = []

    @contextmanager
    def factory(profile: ExtractionProfile, **_kwargs: object) -> Generator[FakeExtractor]:
        versions.append(profile.prompt_version)
        yield FakeExtractor((pair_result(),))

    monkeypatch.setattr("datakeel.worker.kg_runner.create_extractor", factory)
    first = execute_graph(db, prepare_image(db, dataset, file_ids=[text_id]))
    keys = _keys(db)
    text_key = keys["text-kg-v3"]
    identities = {
        item.id: item.extractor
        for item in list_assertions(db)
        if any(anchor.asset_ref.asset_id == text_id for anchor in item.anchors)
    }
    plan = prepare_image(db, dataset)
    prepared = RunKGExtractionParams.model_validate(plan.canonical_params).prepared
    assert prepared is not None
    assert prepared.image_prompt_version == "image-kg-v1"
    assert prepared.profile.prompt_version == "text-kg-v3"
    monkeypatch.setattr("datakeel.kg.prompt.IMAGE_PROMPT_VERSION", "future-image-prompt")
    mixed = execute_graph(db, plan)
    assert first.status == mixed.status == "completed"
    assert (mixed.report.cached, mixed.report.extracted) == (1, 1)
    assert versions == ["text-kg-v3", "image-kg-v1"]
    assert _keys(db)["text-kg-v3"] == text_key
    assert _keys(db)["image-kg-v1"].extractor != text_key.extractor
    assert identities
    assert {
        item.id: item.extractor for item in list_assertions(db) if item.id in identities
    } == identities
