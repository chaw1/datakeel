# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Paired imports retain independently immutable bytes and exclude gold."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from pydantic import ValidationError as ModelValidationError

from datakeel.core.errors import ValidationError
from datakeel.core.evidence_inputs import sample_sidecars
from datakeel.core.models import FileItem
from datakeel.storage.datasets import materialize_files
from datakeel.storage.evidence_import import import_evidence_samples, source_manifest

if TYPE_CHECKING:
    from datakeel.storage.database import Database


def test_paired_import_when_source_changes_retains_original_sidecar_bytes(
    db: Database, tmp_path: Path
) -> None:
    """Ensure moving or changing source files cannot change an imported manifest."""
    root = tmp_path / "inputs"
    directory = root / "val" / "scene-0001"
    directory.mkdir(parents=True)
    (directory / "image.png").write_bytes(b"generated corrupt image")
    (directory / "caption.txt").write_text("A pedestrian.")
    (directory / "annotations.json").write_text('{"annotations": []}')
    (root / "gold.json").write_text('{"label_gaps": ["never read"]}')
    dataset = import_evidence_samples(db, "paired", root)
    version, files = source_manifest(db, dataset.id)
    assert version
    assert dataset.file_count == 1
    sample = sample_sidecars(files[0])
    assert sample.sample_key == "val/scene-0001/image.png"
    assert sample.split == "val"
    assert sample.caption is not None
    assert sample.annotation is not None
    (directory / "caption.txt").write_text("Changed source.")
    restored = materialize_files([sample.caption, sample.annotation])
    assert Path(restored[0].path).read_text() == "A pedestrian."
    assert Path(restored[1].path).read_text() == '{"annotations": []}'


def test_paired_import_when_sidecar_missing_preserves_unknown_input(
    db: Database, tmp_path: Path
) -> None:
    """Keep missing annotations distinct from explicitly empty annotation documents."""
    directory = tmp_path / "train"
    directory.mkdir()
    (directory / "sample.jpg").write_bytes(b"generated sample")
    (directory / "sample.txt").write_text("A person.")
    dataset = import_evidence_samples(db, "missing", tmp_path)
    _, files = source_manifest(db, dataset.id)
    sample = sample_sidecars(files[0])
    assert sample.annotation is None
    assert sample.caption is not None


def test_paired_import_when_caption_json_supplied_retains_json(
    db: Database, tmp_path: Path
) -> None:
    """Keep JSON captions available for the deterministic caption extractor."""
    directory = tmp_path / "train"
    directory.mkdir()
    (directory / "image.png").write_bytes(b"sample")
    (directory / "caption.json").write_text('{"caption": "Night"}')
    dataset = import_evidence_samples(db, "json", tmp_path)
    _, files = source_manifest(db, dataset.id)
    assert sample_sidecars(files[0]).caption is not None


def test_paired_import_when_split_missing_rejects_ambiguous_samples(
    db: Database, tmp_path: Path
) -> None:
    """Reject source directories that would make train/val filtering ambiguous."""
    (tmp_path / "image.png").write_bytes(b"sample")
    with pytest.raises(ValidationError, match="train/ or val/"):
        import_evidence_samples(db, "invalid", tmp_path)


def test_paired_import_when_empty_reports_no_samples(db: Database, tmp_path: Path) -> None:
    """Reject empty imports without creating an empty evidence dataset."""
    with pytest.raises(ValidationError, match="No paired"):
        import_evidence_samples(db, "empty", tmp_path)


def test_source_manifest_when_unknown_rejects_missing_dataset(db: Database) -> None:
    """Report a missing immutable source rather than returning an arbitrary version."""
    with pytest.raises(ValidationError, match="source version"):
        source_manifest(db, "unknown")


def test_sidecar_boundary_when_missing_rejects_unpaired_file() -> None:
    """Require explicit typed pairing metadata before evidence extraction."""
    with pytest.raises(ModelValidationError):
        sample_sidecars(FileItem(path="unused", filename="unused"))
