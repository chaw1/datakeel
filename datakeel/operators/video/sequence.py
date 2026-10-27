# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Frame-accurate thumbnail sequences that locate repeated video at any time offset."""

from __future__ import annotations

from typing import TYPE_CHECKING, NamedTuple, Protocol

import numpy as np
from PIL import Image

from datakeel.core.errors import ValidationError
from datakeel.operators.media.tools import probe_file, run_tool

if TYPE_CHECKING:
    from numpy.typing import NDArray

    from datakeel.core.models import FileItem

THUMBNAIL_WIDTH = 32
THUMBNAIL_HEIGHT = 18
_CHECKS = 8


class Thresholds(Protocol):
    """Expose the per-frame similarity limits shared by matching and extension."""

    max_hamming: float
    max_brightness_difference: float
    max_spatial_difference: float


class Sequence(NamedTuple):
    """Hold every analysed frame of one recording on its own constant-rate timeline."""

    file_id: str
    times: NDArray[np.float64]
    frame_ms: float
    textures: NDArray[np.float32]
    brightness: NDArray[np.float64]
    hashes: NDArray[np.uint64]
    duration_ms: int


class Match(NamedTuple):
    """Pair a candidate frame range with the prior frames that repeat it."""

    prior: Sequence
    first: int
    stop: int
    prior_first: int
    prior_last: int


def _dhash(frame: NDArray[np.uint8]) -> int:
    image = Image.fromarray(frame).convert("L").resize((9, 8), Image.Resampling.BILINEAR)
    pixels = np.asarray(image)
    return int.from_bytes(np.packbits(pixels[:, 1:] > pixels[:, :-1]).tobytes(), "big")


def decode_sequence(file: FileItem, max_fps: float) -> Sequence:
    """Decode every frame up to ``max_fps`` as small RGB thumbnails with exact times."""
    probe = probe_file(file)
    rate = min(probe.frame_rate or max_fps, max_fps)
    content = run_tool(
        [
            "ffmpeg",
            "-v",
            "error",
            "-i",
            file.path,
            "-map",
            "0:v:0",
            "-an",
            "-vf",
            f"fps={rate:.6f},scale={THUMBNAIL_WIDTH}:{THUMBNAIL_HEIGHT}:flags=area",
            "-pix_fmt",
            "rgb24",
            "-f",
            "rawvideo",
            "pipe:1",
        ]
    )
    frame_size = THUMBNAIL_WIDTH * THUMBNAIL_HEIGHT * 3
    if not content or len(content) % frame_size:
        msg = "Video contains no decodable frames"
        raise ValidationError(msg)
    frames = np.frombuffer(content, dtype=np.uint8).reshape(
        -1, THUMBNAIL_HEIGHT, THUMBNAIL_WIDTH, 3
    )
    frame_ms = 1000 / rate
    return Sequence(
        file_id=file.id,
        times=np.arange(len(frames), dtype=np.float64) * frame_ms,
        frame_ms=frame_ms,
        textures=frames.reshape(len(frames), -1).astype(np.float32),
        brightness=frames.reshape(len(frames), -1).mean(axis=1, dtype=np.float64),
        hashes=np.asarray([_dhash(frame) for frame in frames], dtype=np.uint64),
        duration_ms=probe.duration_ms,
    )


def _residual(prior: Sequence, indices: NDArray[np.int64], texture: NDArray[np.float32]) -> float:
    return float(np.min(np.mean(np.abs(prior.textures[indices] - texture), axis=1)))


def frame_matches(
    candidate: Sequence, index: int, prior: Sequence, target_ms: float, limits: Thresholds
) -> bool:
    """Compare one frame with the prior frame nearest its mapped time, tolerating one frame."""
    nearest = int(np.clip(round(target_ms / prior.frame_ms), 0, len(prior.times) - 1))
    if abs(prior.times[nearest] - target_ms) > prior.frame_ms:
        return False
    neighbours = np.arange(max(0, nearest - 1), min(len(prior.times), nearest + 2))
    distances = np.abs(prior.textures[neighbours] - candidate.textures[index]).mean(axis=1)
    best = int(neighbours[int(np.argmin(distances))])
    hamming = int(np.bitwise_count(prior.hashes[best] ^ candidate.hashes[index]))
    return (
        float(distances.min()) <= limits.max_spatial_difference
        and hamming <= limits.max_hamming
        and abs(prior.brightness[best] - candidate.brightness[index])
        <= limits.max_brightness_difference
    )


def _starts(
    candidate: Sequence, first: int, stop: int, prior: Sequence, limit: int
) -> tuple[NDArray[np.int64], NDArray[np.int64], NDArray[np.int64]]:
    checks = np.unique(np.linspace(first, stop - 1, num=min(_CHECKS, stop - first)).round())
    offsets = candidate.times[checks.astype(np.int64)] - candidate.times[first]
    starts = np.arange(limit, dtype=np.int64)
    mapped = np.rint((prior.times[starts, None] + offsets[None, :]) / prior.frame_ms).astype(
        np.int64
    )
    valid = mapped[:, -1] < limit
    return starts[valid], mapped[valid], checks.astype(np.int64)


def find_match(
    candidate: Sequence,
    window: tuple[int, int],
    priors: list[tuple[Sequence, int]],
    limits: Thresholds,
) -> Match | None:
    """Find the closest prior frame range repeating every sampled frame of a window."""
    first, stop = window
    best: tuple[float, Match] | None = None
    for prior, limit in priors:
        starts, mapped, checks = _starts(candidate, first, stop, prior, limit)
        if not starts.size:
            continue
        coarse = np.abs(prior.textures[mapped[:, 0]] - candidate.textures[first]).mean(axis=1)
        for row in np.flatnonzero(coarse <= limits.max_spatial_difference * 2):
            score = _window_score(candidate, checks, prior, mapped[row], limits)
            if score is not None and (best is None or score < best[0]):
                match = Match(prior, first, stop, int(starts[row]), int(mapped[row, -1]))
                best = (score, match)
    return best[1] if best else None


def _window_score(
    candidate: Sequence,
    checks: NDArray[np.int64],
    prior: Sequence,
    mapped: NDArray[np.int64],
    limits: Thresholds,
) -> float | None:
    residuals: list[float] = []
    for index, target in zip(checks.tolist(), mapped.tolist(), strict=True):
        if not frame_matches(candidate, index, prior, float(prior.times[target]), limits):
            return None
        # Score the exact mapping so the true offset beats a neighbouring tolerated one.
        exact = np.asarray([target], dtype=np.int64)
        residuals.append(_residual(prior, exact, candidate.textures[index]))
    return float(np.mean(residuals))
