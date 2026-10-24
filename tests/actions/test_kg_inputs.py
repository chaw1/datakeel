# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Reject unreadable or out-of-scope generated sources before any extraction is queued."""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

import pytest

from datakeel.actions.kg_parameters import RunKGExtractionParams
from datakeel.core.errors import NotFoundError, ValidationError
from datakeel.kg.loader import get_profile
from datakeel.storage.dataset_service import import_paths
from datakeel.storage.evidence_import import source_manifest
from datakeel.storage.kg_store import list_runs
from datakeel.storage.objects import object_store
from tests.kg.integration_helpers import TextDataset, prepare_graph, text_dataset

if TYPE_CHECKING:
    from pathlib import Path

    from datakeel.storage.database import Database


@pytest.mark.parametrize(
    ("content", "reason"), [(b"\xff", "UTF-8"), (b"valid\x00binary", "binary")]
)
def test_prepare_rejects_invalid_utf8_and_binary_content(
    db: Database, tmp_path: Path, content: bytes, reason: str
) -> None:
    """A text filename cannot make invalid input suitable for a model request."""
    path = tmp_path / "invalid.txt"
    path.write_bytes(content)
    imported = import_paths(db, "Generated invalid input", [path])
    version, files = source_manifest(db, imported.id)
    dataset = TextDataset(dataset_id=imported.id, version_id=version, files=tuple(files))
    with pytest.raises(ValidationError, match=reason):
        prepare_graph(db, dataset)
    assert list_runs(db) == ()


def test_prepare_rejects_a_real_version_owned_by_a_different_dataset(
    db: Database, tmp_path: Path
) -> None:
    """A valid version identifier does not authorize mixing two datasets' source scope."""
    first = text_dataset(db, tmp_path / "first", ("Acme uses Widget.",))
    second = text_dataset(db, tmp_path / "second", ("Beta uses Widget.",))
    mixed = first.model_copy(update={"version_id": second.version_id})
    with pytest.raises(NotFoundError, match="does not belong"):
        prepare_graph(db, mixed)
    assert list_runs(db) == ()


def test_prepare_rejects_missing_files_in_an_otherwise_valid_selection(
    db: Database, tmp_path: Path
) -> None:
    """The requested file set cannot silently shrink to only its available subset."""
    dataset = text_dataset(db, tmp_path, ("Acme uses Widget.",))
    with pytest.raises(ValidationError, match="incomplete or unavailable"):
        prepare_graph(db, dataset, file_ids=(dataset.files[0].id, "missing"))
    assert list_runs(db) == ()


def test_prepare_rejects_an_empty_dataset_selection(db: Database, tmp_path: Path) -> None:
    """No-document extraction is rejected while an empty text document remains valid."""
    empty = text_dataset(db, tmp_path / "empty", ())
    with pytest.raises(ValidationError, match="at least one source"):
        prepare_graph(db, empty)
    blank = text_dataset(db, tmp_path / "blank", ("",))
    prepared = RunKGExtractionParams.model_validate(
        prepare_graph(db, blank).canonical_params
    ).prepared
    assert prepared is not None
    assert len(prepared.documents) == 1
    assert prepared.estimate.blocks == 0


def test_prepare_rejects_changed_content_in_its_immutable_source_object(
    db: Database, tmp_path: Path
) -> None:
    """A source whose bytes no longer match the version manifest cannot be approved."""
    dataset = text_dataset(db, tmp_path, ("Acme uses Widget.",))
    key = dataset.files[0].metadata["object_key"]
    assert isinstance(key, str)
    path = object_store().materialize(key)
    path.write_text("Unexpected replacement bytes", encoding="utf-8")
    with pytest.raises(ValidationError, match="immutable manifest"):
        prepare_graph(db, dataset)
    assert list_runs(db) == ()


def test_prepared_text_and_block_offsets_use_nfc_after_utf8_decoding(
    db: Database, tmp_path: Path
) -> None:
    """Manifest byte hashes remain original while all product offsets share normalized text."""
    dataset = text_dataset(db, tmp_path, ("Acme uses Cafe\u0301.",))
    params = RunKGExtractionParams.model_validate(prepare_graph(db, dataset).canonical_params)
    assert params.prepared is not None
    document = params.prepared.documents[0]
    expected = "Acme uses Café."
    assert document.content_revision == dataset.files[0].sha256
    assert document.blocks[0].end == len(expected)
    assert document.blocks[0].content_hash == hashlib.sha256(expected.encode()).hexdigest()


@pytest.mark.parametrize("content", [None, "[broken: secret-fixture", "records: secret-fixture"])
def test_prepare_reports_missing_or_invalid_recordings_without_echoing_contents(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, content: str | None
) -> None:
    """Missing files, YAML errors and invalid recording schemas share a safe located error."""
    dataset = text_dataset(db, tmp_path, ("Acme uses Widget.",))
    path = tmp_path / "recording.yaml"
    if content is not None:
        path.write_text(content, encoding="utf-8")
    profile = get_profile("fake").model_copy(update={"recording": str(path)})
    monkeypatch.setattr("datakeel.storage.kg_preparation.get_profile", lambda _id: profile)
    with pytest.raises(ValidationError, match="Graph recording") as caught:
        prepare_graph(db, dataset)
    assert "secret-fixture" not in str(caught.value)
    assert list_runs(db) == ()
