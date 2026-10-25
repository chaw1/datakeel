# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Verify image progress, mixed-source failures and cancellation at actual worker boundaries."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import func, select

from datakeel.core.kg_queries import KGQuery
from datakeel.storage.dataset_service import import_paths
from datakeel.storage.evidence_import import source_manifest
from datakeel.storage.evidence_store import list_assertions
from datakeel.storage.kg_queries import query_kg
from datakeel.storage.kg_store import list_runs
from datakeel.storage.transcription_rows import TranscriptionRow
from datakeel.worker.queue import DatabaseQueue
from tests.kg.integration_helpers import TextDataset, execute_graph, install_adapter, pair_result
from tests.worker.image_helpers import (
    image_dataset,
    install_transcriber,
    prepare_image,
    transcript,
    use_profile,
)

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

    from datakeel.core.kg_contracts import KGSchema
    from datakeel.core.kg_models import ExtractionResult, TextBlock
    from datakeel.core.transcription_models import (
        ImageInput,
        TranscriptionMode,
        TranscriptionResult,
    )
    from datakeel.storage.database import Database


def test_transcript_checkpoint_keeps_visible_run_state_running(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The newly saved derived document must not send active extraction back to queued state."""
    dataset = image_dataset(db, tmp_path)
    use_profile(monkeypatch)
    install_transcriber(monkeypatch, (transcript(),))
    extractor = install_adapter(monkeypatch, (pair_result(),))
    original = extractor.extract
    observed: list[str] = []

    def extract(block: TextBlock, schema: KGSchema) -> ExtractionResult:
        observed.append(list_runs(db)[0].status)
        return original(block, schema)

    monkeypatch.setattr(extractor, "extract", extract)
    run = execute_graph(db, prepare_image(db, dataset))
    assert run.status == "completed"
    assert observed == ["running"]


def test_failed_image_rerun_preserves_prior_facts_and_completes_mixed_text(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A rejected transcript leaves its old evidence active and does not discard a text source."""
    image_dataset(db, tmp_path)
    text_path = tmp_path / "source.txt"
    text_path.write_text("TextCo uses Database.", encoding="utf-8")
    imported = import_paths(db, "Mixed generated sources", [tmp_path / "image-0.png", text_path])
    version, files = source_manifest(db, imported.id)
    dataset = TextDataset(dataset_id=imported.id, version_id=version, files=tuple(files))
    profile = use_profile(monkeypatch)
    install_transcriber(monkeypatch, (transcript(), transcript().model_copy(update={"text": ""})))
    extractor = install_adapter(monkeypatch, (pair_result(), pair_result("TextCo", "Database")))
    assert execute_graph(db, prepare_image(db, dataset)).status == "completed"
    scope = KGQuery(dataset_id=dataset.dataset_id, version_id=dataset.version_id)
    before = query_kg(db, scope)
    assert {relation.head.name for relation in before.relations} == {"Acme", "TextCo"}
    use_profile(monkeypatch, profile.model_copy(update={"model": "scripted-second"}))
    run = execute_graph(db, prepare_image(db, dataset))
    image_id = next(file.id for file in files if file.filename.endswith(".png"))
    assert run.status == "partial"
    assert run.report.documents == 2
    assert run.report.blocks == 2
    assert run.report.failed == 1
    assert run.report.unexecuted == 0
    assert run.report.cached == 1
    assert run.report.partial_documents == (image_id,)
    assert run.report.failures[0].reason == "transcription:empty"
    assert run.report.transcriptions[0].status == "failed"
    assert extractor.calls == 2
    after = query_kg(db, scope)
    assert {relation.assertion.id for relation in after.relations} == {
        relation.assertion.id for relation in before.relations
    }
    text_relation = next(relation for relation in after.relations if relation.head.name == "TextCo")
    assert text_relation.transcriber is None
    assert text_relation.image_located is None


def test_cancelled_transcription_cannot_publish_cache_or_graph(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cancellation during an outstanding provider call fences both derived text and assertions."""
    dataset = image_dataset(db, tmp_path)
    use_profile(monkeypatch)
    adapter = install_transcriber(monkeypatch, (transcript(),))
    original = adapter.transcribe
    extractor = install_adapter(monkeypatch, (pair_result(),))

    def transcribe(image: ImageInput, mode: TranscriptionMode | None = None) -> TranscriptionResult:
        task_id = list_runs(db)[0].task_id
        assert task_id is not None
        assert DatabaseQueue(db).cancel(task_id)
        return original(image, mode)

    monkeypatch.setattr(adapter, "transcribe", transcribe)
    run = execute_graph(db, prepare_image(db, dataset))
    assert run.status == "failed"
    assert extractor.calls == 0
    assert not list_assertions(db)
    with db.session() as session:
        assert session.scalar(select(func.count()).select_from(TranscriptionRow)) == 0
