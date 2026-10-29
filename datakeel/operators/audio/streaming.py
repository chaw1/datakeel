# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Bounded PCM decoding and temporary seekable audio for multipass measurements."""

from collections.abc import Generator, Iterator
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory, TemporaryFile
from typing import BinaryIO, NamedTuple

import numpy as np
from numpy.typing import NDArray

from datakeel.core.errors import ExecutionError
from datakeel.core.models import FileItem
from datakeel.operators.base import Params
from datakeel.operators.media.tools import (
    input_path,
    media_artifact,
    media_timeout,
    probe_file,
    stream_tool,
)

SAMPLE_RATE = 16000
BLOCK_SAMPLES = 65536
_SAMPLE_BYTES = 8


def channel_blocks(file: FileItem, sample_rate: int = SAMPLE_RATE) -> Iterator[NDArray[np.float64]]:
    """Yield fixed-size PCM blocks, preserving all first-stream audio channels."""
    probe = probe_file(file)
    channels = probe.channels or 1
    stride = channels * _SAMPLE_BYTES
    for raw in stream_tool(
        [
            "ffmpeg",
            "-v",
            "error",
            "-i",
            input_path(file),
            "-map",
            "0:a:0",
            "-ar",
            str(sample_rate),
            "-c:a",
            "pcm_f64le",
            "-f",
            "f64le",
            "pipe:1",
        ],
        BLOCK_SAMPLES * stride,
        timeout=media_timeout(probe.duration_ms),
        allow_partial=True,
    ):
        if len(raw) % stride:
            msg = "ffmpeg produced an incomplete PCM sample"
            raise ExecutionError(msg)
        yield np.frombuffer(raw, dtype="<f8").reshape(-1, channels)


class AudioBuffer(NamedTuple):
    """Seek bounded ranges in a temporary PCM file without mapping the full recording."""

    handle: BinaryIO
    channels: int
    sample_rate: int
    samples: int

    def read(self, start: int, stop: int) -> NDArray[np.float64]:
        """Read a half-open sample range across all channels."""
        stride = self.channels * _SAMPLE_BYTES
        self.handle.seek(start * stride)
        raw = self.handle.read(max(0, min(stop, self.samples) - start) * stride)
        return np.frombuffer(raw, dtype="<f8").reshape(-1, self.channels)

    def blocks(self, size: int | None = None) -> Iterator[tuple[int, NDArray[np.float64]]]:
        """Yield independently allocated bounded ranges for repeated measurement passes."""
        block_size = size or BLOCK_SAMPLES
        for start in range(0, self.samples, block_size):
            yield start, self.read(start, start + block_size)

    def strongest_channel(self) -> int:
        """Choose one channel by whole-recording energy without phase cancellation."""
        energy = np.zeros(self.channels, dtype=np.float64)
        for _, block in self.blocks():
            energy += np.square(block).sum(axis=0)
        return int(np.argmax(energy))


@contextmanager
def audio_buffer(file: FileItem, sample_rate: int = SAMPLE_RATE) -> Generator[AudioBuffer]:
    """Spool streamed PCM to an automatically removed scratch file for global statistics."""
    channels = probe_file(file).channels or 1
    samples = 0
    with TemporaryFile() as handle:
        for block in channel_blocks(file, sample_rate):
            handle.write(block.tobytes())
            samples += len(block)
        handle.flush()
        yield AudioBuffer(handle, channels, sample_rate, samples)


def stream_artifact(
    file: FileItem,
    output_dir: Path,
    arguments: list[str],
    operator: str,
    params: Params,
    **timing: int | None,
) -> FileItem:
    """Store PCM transformation output in chunks while preserving original pipe bytes."""
    with TemporaryDirectory(prefix="datakeel-audio-") as temporary:
        path = Path(temporary) / "output.wav"
        with path.open("wb") as handle:
            for raw in stream_tool(
                arguments,
                1 << 20,
                timeout=media_timeout(probe_file(file).duration_ms),
                allow_partial=True,
            ):
                handle.write(raw)
        return media_artifact(file, output_dir, path, "wav", operator, params, **timing)
