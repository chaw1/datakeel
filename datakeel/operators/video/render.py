# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Encode deterministic MP4 artifacts with externally installed ffmpeg."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING

from datakeel.operators.media.tools import input_path, media_timeout, probe_file, run_tool

if TYPE_CHECKING:
    from datakeel.core.models import FileItem


def render(
    file: FileItem,
    filters: str = "null",
    start_ms: float = 0,
    end_ms: float | None = None,
    frame_count: int | None = None,
) -> bytes:
    """Accurately decode a time range and preserve the first optional audio stream.

    The seek is an input option, so ffmpeg jumps to the nearest earlier keyframe and
    decodes only from there instead of from the start of the recording; frames
    before ``start_ms`` are still discarded exactly. The encoder runs on one thread
    because its output depends on the thread count.
    """
    probe = probe_file(file)
    span = (probe.duration_ms if end_ms is None else end_ms) - start_ms
    arguments = ["ffmpeg", "-v", "error", "-fflags", "+bitexact"]
    if start_ms > 0:
        arguments.extend(["-ss", f"{start_ms / 1000:.6f}"])
    arguments.extend(["-i", input_path(file)])
    if end_ms is not None:
        arguments.extend(["-t", f"{(end_ms - start_ms) / 1000:.6f}"])
    if frame_count is not None:
        arguments.extend(["-frames:v", str(frame_count)])
    arguments.extend(
        [
            "-map",
            "0:v:0",
            "-map",
            "0:a:0?",
            "-vf",
            filters,
            "-map_metadata",
            "-1",
            "-c:v",
            "mpeg4",
            "-q:v",
            "3",
            "-threads",
            "1",
            "-flags:v",
            "+bitexact",
            "-c:a",
            "aac",
            "-flags:a",
            "+bitexact",
            "-fflags",
            "+bitexact",
            "-movflags",
            "+faststart",
            "-f",
            "mp4",
        ]
    )
    timeout = media_timeout(max(0, round(span)), probe.width, probe.height)
    with TemporaryDirectory(prefix="datakeel-video-") as temporary:
        destination = Path(temporary) / "output.mp4"
        run_tool([*arguments, str(destination)], timeout=timeout)
        return destination.read_bytes()
