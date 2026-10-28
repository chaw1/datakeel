# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Encode deterministic MP4 artifacts with externally installed ffmpeg."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING

from datakeel.operators.media.tools import input_path, media_timeout, probe_file, run_tool
from datakeel.operators.video.frames import seek_plan

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

    ``start_ms`` and ``end_ms`` count from the first video frame. An input-side seek
    enters just before the last keyframe at or before ``start_ms`` (see
    :func:`seek_plan`), so ffmpeg decodes only from there instead of from the start of
    the recording, also in containers without a seek index; an output-side seek then
    discards the frames before ``start_ms`` exactly. The encoder runs on one thread
    because its output depends on the thread count.
    """
    probe = probe_file(file)
    span = (probe.duration_ms if end_ms is None else end_ms) - start_ms
    entry_ms = skip_ms = origin_ms = 0.0
    if start_ms > 0 or end_ms is not None:
        entry_ms, skip_ms, origin_ms = seek_plan(file, start_ms)
    arguments = ["ffmpeg", "-v", "error", "-fflags", "+bitexact"]
    if entry_ms > 0:
        arguments.extend(["-ss", f"{entry_ms / 1000:.6f}"])
    arguments.extend(["-i", input_path(file)])
    if skip_ms > 0:
        arguments.extend(["-ss", f"{skip_ms / 1000:.6f}"])
    if end_ms is not None:
        # A clip from the start keeps whatever precedes the first video frame.
        lead = origin_ms if start_ms <= 0 else 0.0
        arguments.extend(["-t", f"{(end_ms - start_ms + lead) / 1000:.6f}"])
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
    decoded = span + max(0.0, skip_ms)
    timeout = media_timeout(max(0, round(decoded)), probe.width, probe.height)
    with TemporaryDirectory(prefix="datakeel-video-") as temporary:
        destination = Path(temporary) / "output.mp4"
        run_tool([*arguments, str(destination)], timeout=timeout)
        return destination.read_bytes()
