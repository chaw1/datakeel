# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Generate isolated recordings using ffmpeg's built-in lavfi sources."""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING, Protocol

import pytest

from datakeel.core.models import FileItem
from datakeel.operators.media.tools import run_tool

if TYPE_CHECKING:
    from pathlib import Path


class VideoFactory(Protocol):
    """Generate a local lavfi video, with an optional synthesized audio track."""

    def __call__(
        self, expression: str = "testsrc2=size=160x96:rate=10:duration=2", *, audio: bool = False
    ) -> FileItem:
        """Materialize generated signal content as a video file."""
        ...


@pytest.fixture
def make_video(tmp_path: Path) -> VideoFactory:
    """Expose a generated-video factory without checked-in media bytes."""
    generated = 0

    def make(
        expression: str = "testsrc2=size=160x96:rate=10:duration=2", *, audio: bool = False
    ) -> FileItem:
        nonlocal generated
        generated += 1
        path = tmp_path / f"source-{generated}.mkv"
        arguments = ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", expression]
        if audio:
            arguments.extend(["-f", "lavfi", "-i", "sine=frequency=347:sample_rate=16000"])
        arguments.extend(
            ["-c:v", "mpeg4", "-q:v", "2", "-c:a", "pcm_s16le", "-shortest", str(path)]
        )
        run_tool(arguments)
        content = path.read_bytes()
        return FileItem(
            path=str(path),
            filename=path.name,
            size=len(content),
            modality="video",
            sha256=hashlib.sha256(content).hexdigest(),
        )

    return make
