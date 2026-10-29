# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Encode deterministic MP4 artifacts with externally installed ffmpeg."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING

from datakeel.operators.media.tools import input_path, media_timeout, probe_file, run_tool
from datakeel.operators.video.frames import frame_times, seek_plan

if TYPE_CHECKING:
    from datakeel.core.models import FileItem

# Bit-exact MPEG-4 video and AAC audio in a fast-start MP4, without source metadata.
_ENCODE = (
    *("-map_metadata", "-1", "-c:v", "mpeg4", "-q:v", "3", "-threads", "1"),
    *("-flags:v", "+bitexact", "-c:a", "aac", "-flags:a", "+bitexact"),
    *("-fflags", "+bitexact", "-movflags", "+faststart", "-f", "mp4"),
)


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
    the recording, also in containers without a seek index; a trim filter then discards
    the frames before ``start_ms`` exactly. The output starts at the first kept video
    frame: its timestamp becomes zero and the audio is cut at the same instant, so the
    clip never opens on a gap between the timeline origin and its first picture.
    ffmpeg's constant-rate sync fills such a gap differently per version (6.1 duplicates
    the first frame, 9.0 moves it to the next frame slot), and audio that precedes the
    first video frame would otherwise desynchronize the clip. The encoder runs on one
    thread because its output depends on the thread count.
    """
    probe = probe_file(file)
    span = (probe.duration_ms if end_ms is None else end_ms) - start_ms
    entry_ms, skip_ms, origin_ms = seek_plan(file, start_ms)
    first_ms = _first_frame_ms(file, start_ms)
    # ffmpeg shifts input timestamps so the seek point (or the container start) is zero;
    # the first kept video frame then sits here.
    clip_origin = f"{(origin_ms + first_ms - entry_ms) / 1000:.6f}"
    arguments = ["ffmpeg", "-v", "error", "-fflags", "+bitexact"]
    if entry_ms > 0:
        arguments.extend(["-ss", f"{entry_ms / 1000:.6f}"])
    arguments.extend(["-i", input_path(file)])
    if end_ms is not None:
        arguments.extend(["-t", f"{(end_ms - first_ms) / 1000:.6f}"])
    if frame_count is not None:
        arguments.extend(["-frames:v", str(frame_count)])
    video = f"trim=start={skip_ms / 1000:.6f}," if skip_ms > 0 else ""
    video += f"setpts=PTS-STARTPTS,{filters}"
    audio = f"atrim=start={clip_origin},asetpts=PTS-{clip_origin}/TB"
    arguments.extend(["-map", "0:v:0", "-map", "0:a:0?", "-vf", video, "-af", audio, *_ENCODE])
    decoded = span + max(0.0, skip_ms)
    timeout = media_timeout(max(0, round(decoded)), probe.width, probe.height)
    with TemporaryDirectory(prefix="datakeel-video-") as temporary:
        destination = Path(temporary) / "output.mp4"
        run_tool([*arguments, str(destination)], timeout=timeout)
        return destination.read_bytes()


def _first_frame_ms(file: FileItem, start_ms: float) -> float:
    """Return the time of the first video frame at or after ``start_ms``."""
    if start_ms <= 0:
        return 0.0
    times = frame_times(file)
    return next((time for time in times if time >= start_ms), times[-1])
