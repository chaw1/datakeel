# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Actual-input cache dependencies, versioned context, and bounded global cache keys."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from datakeel.core.evidence_inputs import sample_sidecars
from datakeel.core.evidence_models import ExtractorRef
from datakeel.core.models import JsonDocument
from datakeel.evidence import runtime_inputs
from datakeel.evidence.runtime_inputs import cache_requests, prepare_inputs, prepare_node_inputs
from datakeel.storage.datasets import materialize_files
from datakeel.storage.evidence_import import source_manifest
from tests.evidence.test_execution import seed_evidence

if TYPE_CHECKING:
    import pytest

    from datakeel.storage.database import Database


def test_near_duplicate_keys_include_every_peer_but_remain_constant_size(
    db: Database,
    tmp_path: Path,
) -> None:
    """Invalidate every pairwise slot when another source changes without quadratic payloads."""
    dataset_id = seed_evidence(db, tmp_path / "samples")
    version, files = source_manifest(db, dataset_id)
    files = prepare_inputs(materialize_files(files), version)
    extractor = ExtractorRef(id="evidence.near_duplicate", version="1.0")
    params = JsonDocument({"extractor_version": "1.0"})
    before = cache_requests(files, extractor, params)
    assert all(len(entry.key.inputs) == 2 for entry in before)
    assert len(before[0].model_dump_json()) < 1500
    Path(files[-1].path).write_bytes(b"changed peer content")
    after = cache_requests(files, extractor, params)
    assert all(
        left.key.digest() != right.key.digest() for left, right in zip(before, after, strict=True)
    )


def test_caption_cache_ignores_path_changes_but_tracks_sidecar_content(
    db: Database,
    tmp_path: Path,
) -> None:
    """Reuse content after relocation and invalidate when the actual caption changes."""
    dataset_id = seed_evidence(db, tmp_path / "samples")
    version, source = source_manifest(db, dataset_id)
    files = prepare_inputs(materialize_files(source[:1]), version)
    extractor = ExtractorRef(id="evidence.caption_mentions", version="1.0")
    params = JsonDocument({"extractor_version": "1.0"})
    before = cache_requests(files, extractor, params)
    moved = tmp_path / "relocated.png"
    moved.write_bytes(Path(files[0].path).read_bytes())
    renamed = [files[0].model_copy(update={"path": str(moved), "filename": "renamed.png"})]
    assert cache_requests(renamed, extractor, params)[0].key == before[0].key
    caption = files[0].metadata["evidence_sample"]["caption"]
    Path(caption["path"]).write_text("A changed generated caption")
    assert cache_requests(renamed, extractor, params)[0].key != before[0].key


def test_node_snapshot_hashes_each_path_once_and_refreshes_next_call(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Anchors and cache keys share current bytes without retaining stale input revisions."""
    dataset_id = seed_evidence(db, tmp_path / "samples")
    version, source = source_manifest(db, dataset_id)
    files = materialize_files(source[:2])
    extractor = ExtractorRef(id="evidence.caption_mentions", version="1.0")
    params = JsonDocument({"extractor_version": "1.0"})
    original = runtime_inputs.digest
    calls: list[Path] = []

    def digest(path: Path) -> str:
        calls.append(path)
        return original(path)

    monkeypatch.setattr(runtime_inputs, "digest", digest)
    before = prepare_node_inputs(files, version, extractor, params)
    assert len(calls) == len(set(calls))
    caption = sample_sidecars(before.files[0]).caption
    assert caption is not None
    assert before.requests[0].key.inputs[0].content_revision == caption.sha256
    Path(caption.path).write_text("Changed after the first node snapshot")
    after = prepare_node_inputs(files, version, extractor, params)
    assert after.requests[0].key != before.requests[0].key
    assert after.requests[1].key == before.requests[1].key
