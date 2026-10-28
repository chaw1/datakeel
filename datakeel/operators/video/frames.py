# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Read frame presentation times and assemble half-open issue intervals."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING

from datakeel.core.errors import ExecutionError, ValidationError
from datakeel.core.media_models import MediaInterval
from datakeel.operators.media.tools import input_path, media_timeout, probe_file, run_tool

if TYPE_CHECKING:
    from datakeel.core.models import FileItem


def intervals(
    flags: list[bool], code: str, sample_fps: float, duration_ms: int, minimum_ms: int = 0
) -> list[MediaInterval]:
    """Coalesce sampled flags into bounded half-open source time intervals."""
    result: list[MediaInterval] = []
    start: int | None = None
    for index, flagged in enumerate([*flags, False]):
        if flagged and start is None:
            start = index
        elif not flagged and start is not None:
            start_ms = min(duration_ms, round(start * 1000 / sample_fps))
            end_ms = min(duration_ms, round(index * 1000 / sample_fps))
            if end_ms > start_ms and end_ms - start_ms >= minimum_ms:
                result.append(MediaInterval(code=code, start_ms=start_ms, end_ms=end_ms))
            start = None
    return result


def frame_times(file: FileItem) -> list[float]:
    """Read video presentation times in source-local milliseconds, cached per file version.

    Times come from the stored packets, which needs no decoding; a stream without
    packet timestamps falls back to decoding every frame once.
    """
    return list(_frame_times(*_version(file)))


def seek_plan(file: FileItem, start_ms: float) -> tuple[float, float, float]:
    """Return ``(entry_ms, skip_ms, origin_ms)`` for a clip starting at ``start_ms``.

    ``start_ms`` counts from the first video frame, as :func:`frame_times` does, while
    ffmpeg's ``-ss`` counts from the container start; ``origin_ms`` is the gap between
    them (an MPEG-TS capture's audio typically starts before its video). The input-side
    seek ``entry_ms`` lands just before the last keyframe at or before the start: a
    container without a seek index (MPEG-TS) may otherwise land on the *following*
    keyframe, losing frames or never delivering them. The output-side seek ``skip_ms``
    then discards the frames before the start exactly. Without packet timestamps the
    keyframes are unknown and the clip is decoded from the beginning.
    """
    path, size, modified, timeout = _version(file)
    times, keyframes = _packets(path, size, modified, timeout)
    if not times:
        return 0.0, max(0.0, start_ms), 0.0
    container = _container_start_ms(path, timeout)
    origin = times[0] - container if container is not None else 0.0
    if start_ms <= 0:
        return 0.0, 0.0, origin
    earlier = [key - times[0] for key in keyframes if key - times[0] <= start_ms]
    entry = max(0.0, origin + earlier[-1] - _ENTRY_MARGIN_MS) if earlier else 0.0
    return entry, origin + start_ms - entry, origin


# Enter this far before a keyframe, so a seek resolving to the following keyframe
# still lands on it.
_ENTRY_MARGIN_MS = 1.0


def _version(file: FileItem) -> tuple[str, int, int, float]:
    path = Path(input_path(file))
    try:
        status = path.stat()
    except OSError as error:
        msg = f"Recording is not readable: {type(error).__name__}"
        raise ExecutionError(msg) from error
    probe = probe_file(file)
    timeout = media_timeout(probe.duration_ms, probe.width, probe.height)
    return str(path), status.st_size, status.st_mtime_ns, timeout


@lru_cache(maxsize=8)
def _frame_times(path: str, size: int, modified_ns: int, timeout: float) -> tuple[float, ...]:
    times = list(_packets(path, size, modified_ns, timeout)[0]) or _decoded_times(path, timeout)
    if not times:
        msg = "Video contains no timestamped frames"
        raise ValidationError(msg)
    return tuple(timestamp - times[0] for timestamp in times)


@lru_cache(maxsize=8)
def _packets(
    path: str, _size: int, _modified_ns: int, timeout: float
) -> tuple[tuple[float, ...], tuple[float, ...]]:
    """Return sorted kept packet times and keyframe times, in absolute milliseconds."""
    times, keyframes = _packet_times(path, timeout)
    return tuple(sorted(times)), tuple(sorted(keyframes))


def _packet_times(path: str, timeout: float) -> tuple[list[float], list[float]]:
    """Return kept video packet timestamps and keyframe timestamps.

    Packets flagged for discard are not shown; without timestamps both are empty.
    """
    listing = _listing(path, "packet=pts_time,flags", timeout)
    times: list[float] = []
    keyframes: list[float] = []
    for line in listing:
        stamp, _, flags = line.partition(",")
        if stamp in {"", "N/A"}:
            return [], []
        if "D" not in flags:
            times.append(float(stamp) * 1000)
            if "K" in flags:
                keyframes.append(float(stamp) * 1000)
    return times, keyframes


def _container_start_ms(path: str, timeout: float) -> float | None:
    """Return the container start time that ffmpeg's ``-ss`` counts from."""
    content = run_tool(
        ["ffprobe", "-v", "error", "-show_entries", "format=start_time", "-of", "csv=p=0", path],
        timeout=timeout,
    )
    try:
        return float(content.decode(errors="replace").strip()) * 1000
    except ValueError:
        return None


def _decoded_times(path: str, timeout: float) -> list[float]:
    listing = _listing(path, "frame=best_effort_timestamp_time", timeout)
    return sorted(
        float(line.split(",")[0]) * 1000
        for line in listing
        if line.split(",")[0].strip() not in {"", "N/A"}
    )


def _listing(path: str, entries: str, timeout: float) -> list[str]:
    content = run_tool(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            entries,
            "-of",
            "csv=p=0",
            path,
        ],
        timeout=timeout,
    )
    return content.decode(errors="replace").splitlines()
