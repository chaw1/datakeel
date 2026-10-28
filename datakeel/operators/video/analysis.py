# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Decode a recording once into per-frame signal statistics and repeat-search thumbnails.

Invalid-frame detection and repeat search read the same cached pass, so a long
recording is decoded once (multithreaded) and never held in memory at full size:
grayscale analysis frames are streamed and reduced to a few numbers each, and only
the 32x18 thumbnails are kept.
"""

from __future__ import annotations

import tempfile
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple

import numpy as np

from datakeel.core.errors import ExecutionError, ValidationError
from datakeel.operators.media.tools import input_path, media_timeout, probe_file, stream_tool

if TYPE_CHECKING:
    from numpy.typing import NDArray

    from datakeel.core.models import FileItem

FRAME_WIDTH = 160
FRAME_HEIGHT = 90
BLOCK = 10
THUMBNAIL_WIDTH = 32
THUMBNAIL_HEIGHT = 18
_BATCH = 256
_ANALYSIS_TIMEOUT_FACTOR = 2


class VideoAnalysis(NamedTuple):
    """Hold one decoded pass on a constant-rate timeline starting at zero.

    Change statistics at index ``i`` compare frame ``i`` with frame ``i - 1``
    (index 0 is zero): ``change`` is the mean absolute difference, ``peak`` the
    largest 10x10-block mean absolute difference and ``shift`` the signed mean.
    """

    rate: float
    frame_ms: float
    duration_ms: int
    mean: NDArray[np.float64]
    deviation: NDArray[np.float64]
    detail: NDArray[np.float64]
    change: NDArray[np.float64]
    peak: NDArray[np.float64]
    shift: NDArray[np.float64]
    thumbnails: NDArray[np.uint8]

    @property
    def frame_count(self) -> int:
        """Return the number of analysed frames."""
        return len(self.mean)

    def luma(self) -> NDArray[np.float32]:
        """Return BT.601 luma of the thumbnails as ``(frames, 576)`` float32."""
        pixels = self.thumbnails.reshape(self.frame_count, -1, 3).astype(np.float32)
        weights = np.asarray([0.299, 0.587, 0.114], dtype=np.float32)
        return pixels @ weights


def analysis_rate(frame_rate: float, max_fps: float) -> float:
    """Analyse every frame up to ``max_fps``; faster video is sampled evenly."""
    return min(frame_rate or max_fps, max_fps)


def analyse(file: FileItem, max_fps: float) -> VideoAnalysis:
    """Return the cached single-pass analysis of this file version at ``max_fps``."""
    path = Path(input_path(file))
    try:
        status = path.stat()
    except OSError as error:
        msg = f"Recording is not readable: {type(error).__name__}"
        raise ExecutionError(msg) from error
    return _analyse(str(path), status.st_size, status.st_mtime_ns, max_fps)


@lru_cache(maxsize=2)
def _analyse(path: str, _size: int, _modified_ns: int, max_fps: float) -> VideoAnalysis:
    from datakeel.core.models import FileItem  # noqa: PLC0415  # Runtime-only construction.

    probe = probe_file(FileItem(path=path, filename=Path(path).name, modality="video"))
    rate = analysis_rate(probe.frame_rate, max_fps)
    graph = (
        f"[0:v:0]fps={rate:.6f},split=2[a][b];"
        f"[a]scale={FRAME_WIDTH}:{FRAME_HEIGHT}:flags=area,format=gray[g];"
        f"[b]scale={THUMBNAIL_WIDTH}:{THUMBNAIL_HEIGHT}:flags=area,format=rgb24[t]"
    )
    timeout = _ANALYSIS_TIMEOUT_FACTOR * media_timeout(probe.duration_ms, probe.width, probe.height)
    with tempfile.TemporaryDirectory(prefix="datakeel-analysis-") as temporary:
        thumbnails_path = Path(temporary) / "thumbnails.rgb"
        arguments = [
            "ffmpeg",
            "-v",
            "error",
            "-i",
            path,
            "-filter_complex",
            graph,
            "-map",
            "[g]",
            "-f",
            "rawvideo",
            "pipe:1",
            "-map",
            "[t]",
            "-f",
            "rawvideo",
            str(thumbnails_path),
        ]
        statistics = _Accumulator()
        batch: list[bytes] = []
        for record in stream_tool(arguments, FRAME_WIDTH * FRAME_HEIGHT, timeout=timeout):
            batch.append(record)
            if len(batch) == _BATCH:
                statistics.add(batch)
                batch = []
        statistics.add(batch)
        thumbnails = np.fromfile(thumbnails_path, dtype=np.uint8)
    frame_size = THUMBNAIL_WIDTH * THUMBNAIL_HEIGHT * 3
    if not statistics.count or thumbnails.size != statistics.count * frame_size:
        msg = "Video contains no decodable frames"
        raise ValidationError(msg)
    return VideoAnalysis(
        rate=rate,
        frame_ms=1000 / rate,
        duration_ms=probe.duration_ms,
        thumbnails=thumbnails.reshape(-1, THUMBNAIL_HEIGHT, THUMBNAIL_WIDTH, 3),
        **statistics.arrays(),
    )


class _Accumulator:
    """Reduce streamed grayscale frames to per-frame statistics in small batches."""

    def __init__(self) -> None:
        self.parts: dict[str, list[NDArray[np.float64]]] = {
            key: [] for key in ("mean", "deviation", "detail", "change", "peak", "shift")
        }
        self.previous: NDArray[np.float32] | None = None
        self.count = 0

    def add(self, records: list[bytes]) -> None:
        if not records:
            return
        frames = (
            np.frombuffer(b"".join(records), dtype=np.uint8)
            .reshape(-1, FRAME_HEIGHT, FRAME_WIDTH)
            .astype(np.float32)
        )
        previous = frames[:1] if self.previous is None else self.previous[None]
        difference = frames - np.concatenate((previous, frames[:-1]))
        blocks = np.abs(difference).reshape(
            len(frames), FRAME_HEIGHT // BLOCK, BLOCK, FRAME_WIDTH // BLOCK, BLOCK
        )
        center = frames[:, 1:-1, 1:-1]
        laplacian = (
            frames[:, :-2, 1:-1]
            + frames[:, 2:, 1:-1]
            + frames[:, 1:-1, :-2]
            + frames[:, 1:-1, 2:]
            - 4 * center
        )
        values = {
            "mean": frames.mean(axis=(1, 2)),
            "deviation": frames.std(axis=(1, 2)),
            "detail": laplacian.var(axis=(1, 2)),
            "change": np.abs(difference).mean(axis=(1, 2)),
            "peak": blocks.mean(axis=(2, 4)).max(axis=(1, 2)),
            "shift": difference.mean(axis=(1, 2)),
        }
        for key, value in values.items():
            self.parts[key].append(value.astype(np.float64))
        self.previous = frames[-1]
        self.count += len(frames)

    def arrays(self) -> dict[str, NDArray[np.float64]]:
        return {
            key: np.concatenate(parts) if parts else np.zeros(0, dtype=np.float64)
            for key, parts in self.parts.items()
        }
