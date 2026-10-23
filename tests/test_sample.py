# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Generated fixtures are complete, deterministic, and contain declared empty cases."""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

from PIL import Image

from datakeel.sample import generate_samples

if TYPE_CHECKING:
    from pathlib import Path


def test_sample_generation_when_run_twice_produces_reproducible_four_hundred_files(
    tmp_path: Path,
) -> None:
    """Verify sample generation when run twice produces reproducible four hundred files."""
    paths = generate_samples(tmp_path / "samples")
    hashes = [hashlib.sha256(path.read_bytes()).hexdigest() for path in paths]
    regenerated = generate_samples(tmp_path / "samples")
    assert hashes == [hashlib.sha256(path.read_bytes()).hexdigest() for path in regenerated]
    assert len(paths) == 400


def test_sample_generation_when_completed_contains_expected_modalities_and_empty_cases(
    tmp_path: Path,
) -> None:
    """Verify sample generation when completed contains expected modalities and empty cases."""
    paths = generate_samples(tmp_path / "samples")
    images = [path for path in paths if path.suffix == ".png"]
    texts = [path for path in paths if path.suffix == ".txt"]
    assert len(images) == len(texts) == 200
    with Image.open(images[0]) as image:
        assert image.size == (192, 128)
        assert image.mode == "RGB"
    assert [path.name for path in texts if not path.read_text(encoding="utf-8")] == [
        "note-198.txt",
        "note-199.txt",
    ]
