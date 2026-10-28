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
    path = Path(input_path(file))
    try:
        status = path.stat()
    except OSError as error:
        msg = f"Recording is not readable: {type(error).__name__}"
        raise ExecutionError(msg) from error
    probe = probe_file(file)
    timeout = media_timeout(probe.duration_ms, probe.width, probe.height)
    return list(_frame_times(str(path), status.st_size, status.st_mtime_ns, timeout))


@lru_cache(maxsize=8)
def _frame_times(path: str, _size: int, _modified_ns: int, timeout: float) -> tuple[float, ...]:
    times = sorted(_packet_times(path, timeout)) or _decoded_times(path, timeout)
    if not times:
        msg = "Video contains no timestamped frames"
        raise ValidationError(msg)
    return tuple(timestamp - times[0] for timestamp in times)


def _packet_times(path: str, timeout: float) -> list[float]:
    """Return kept video packet timestamps; packets flagged for discard are not shown."""
    listing = _listing(path, "packet=pts_time,flags", timeout)
    times: list[float] = []
    for line in listing:
        stamp, _, flags = line.partition(",")
        if stamp in {"", "N/A"}:
            return []
        if "D" not in flags:
            times.append(float(stamp) * 1000)
    return times


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
