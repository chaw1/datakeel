# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Build all audio test recordings locally from ffmpeg's lavfi sources."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

import pytest

from datakeel.core.models import FileItem
from datakeel.operators.media.tools import run_tool

if TYPE_CHECKING:
    from pathlib import Path


class AudioFactory(Protocol):
    """Create a generated lavfi recording with optional deterministic filtering."""

    def __call__(self, source: str, filters: str = "anull") -> FileItem:
        """Materialize one isolated PCM recording."""
        ...


@pytest.fixture
def make_audio(tmp_path: Path) -> AudioFactory:
    """Provide a lavfi-only fixture factory without real media assets."""
    counter = 0

    def make(source: str, filters: str = "anull") -> FileItem:
        nonlocal counter
        counter += 1
        path = tmp_path / f"generated-{counter}.wav"
        content = run_tool(
            [
                "ffmpeg",
                "-v",
                "error",
                "-f",
                "lavfi",
                "-i",
                source,
                "-af",
                filters,
                "-c:a",
                "pcm_s16le",
                "-f",
                "wav",
                "pipe:1",
            ]
        )
        path.write_bytes(content)
        return FileItem(
            id=f"audio-{counter}",
            path=str(path),
            filename=path.name,
            size=len(content),
            modality="audio",
        )

    return make
