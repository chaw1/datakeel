# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Image demonstrations preserve recording keys and label synthetic quality failures."""

import hashlib
from pathlib import Path

from datakeel.core.transcription_models import TranscriptionRecording
from datakeel.kg.loader import contracts_path, load_contract
from datakeel.sample_image_kg import IMAGE_DEMO_NAMES, generate_image_kg_samples


def test_image_samples_preserve_original_bytes_and_identify_scripted_failure(
    tmp_path: Path,
) -> None:
    """Include clear, scanned and structured evidence without regenerating recorded pixels."""
    files = generate_image_kg_samples(tmp_path)
    assert len(files.recorded) == 10
    assert len(files.paths) == 11
    root = contracts_path()
    for path, name in zip(files.recorded, IMAGE_DEMO_NAMES, strict=True):
        assert path.read_bytes() == (root / "eval/image/images" / name).read_bytes()
    assert any("scan" in path.name for path in files.recorded)
    assert any(path.stem == "b09" for path in files.recorded)
    recording = load_contract(root / "demo/image-truncated.yaml", TranscriptionRecording)
    assert "Scripted" in recording.source
    assert recording.records[0].backend == "fake"
    assert recording.records[0].finish_reason == "length"
    assert (
        recording.records[0].image_hash == hashlib.sha256(files.truncated.read_bytes()).hexdigest()
    )
