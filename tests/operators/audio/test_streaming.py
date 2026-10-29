# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Block boundaries preserve the original complete-track numerical definitions."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import pytest

from datakeel.core.errors import ExecutionError
from datakeel.operators.audio import clipping, clipping_stream, fingerprint, streaming
from datakeel.operators.audio.common import activity, measure_activity, runs
from datakeel.operators.audio.fingerprint import _mel_filters
from datakeel.operators.audio.flat_tops import flat_tops
from datakeel.operators.audio.params import ActivityParams, ClippingParams
from datakeel.operators.media.tools import input_path, probe_file, run_tool

if TYPE_CHECKING:
    from numpy.typing import NDArray

    from datakeel.core.models import FileItem
    from tests.operators.audio.conftest import AudioFactory


def _decoded(file: FileItem, rate: int) -> NDArray[np.float64]:
    raw = run_tool(
        ["ffmpeg", "-v", "error", "-i", input_path(file), "-ar", str(rate), "-f", "f64le", "pipe:1"]
    )
    return np.frombuffer(raw, dtype="<f8").reshape(-1, probe_file(file).channels)


def test_activity_carries_partial_frames_across_decode_blocks(
    make_audio: AudioFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Uneven decode chunks retain energy at every frame and the final partial frame."""
    source = make_audio(
        r"aevalsrc=if(between(t\,0.035\,0.143)\,0.2*sin(2*PI*651*t)\,0):s=16000:d=0.217"
    )
    monkeypatch.setattr(streaming, "BLOCK_SAMPLES", 257)
    channels = _decoded(source, 16000)
    samples = np.sqrt(np.mean(np.square(channels), axis=1))
    for frame_ms in (5, 20, 25):
        params = ActivityParams(frame_ms=frame_ms, min_activity_ms=0, min_silence_ms=0)
        assert measure_activity(source, params) == activity(samples, params)


def _reference_signature(samples: NDArray[np.float64]) -> NDArray[np.float64]:
    emphasized = np.append(samples[0], samples[1:] - 0.97 * samples[:-1])
    frames = np.lib.stride_tricks.sliding_window_view(emphasized, 400)[::160]
    spectrum = np.abs(np.fft.rfft(frames * np.hamming(400), n=512)) ** 2
    mel = spectrum @ _mel_filters().T
    floor = max(float(mel.max()) * 1e-6, 1e-30)
    basis = np.cos(np.pi / 26 * (np.arange(26) + 0.5)[None, :] * np.arange(1, 14)[:, None])
    coefficients = np.log(np.maximum(mel, floor)) @ (basis * np.sqrt(2 / 26)).T
    count = len(coefficients) // 5
    return coefficients[: count * 5].reshape(count, 5, 13).mean(axis=1)


def test_fingerprint_preserves_preemphasis_overlap_and_global_floor(
    make_audio: AudioFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Window overlap and the full-track floor match the prior whole-matrix definition."""
    source = make_audio(
        r"aevalsrc=0.01*sin(2*PI*413*t)|if(lt(t\,0.35)\,0.001\,0.3)*sin(2*PI*967*t):s=16000:d=0.933"
    )
    monkeypatch.setattr(streaming, "BLOCK_SAMPLES", 257)
    monkeypatch.setattr(fingerprint, "_BATCH_FRAMES", 10)
    channels = _decoded(source, 16000)
    samples = channels[:, int(np.argmax(np.square(channels).mean(axis=0)))]
    expected = _reference_signature(samples)
    actual = fingerprint.file_signature(source)
    assert actual.duration_ms == 933
    assert actual.blocks.shape == expected.shape
    np.testing.assert_allclose(actual.blocks, expected, atol=1e-10, rtol=1e-10)


def _reference_clipping(
    samples: NDArray[np.float32], rate: int, params: ClippingParams
) -> NDArray[np.bool_]:
    result = np.zeros(samples.shape, dtype=np.bool_)
    window = max(1, rate * params.window_ms // 1000)
    for channel in range(samples.shape[1]):
        signal = samples[:, channel]
        for start, end in runs(np.abs(signal) >= params.threshold):
            if end - start >= params.min_consecutive_samples and np.ptp(signal[start:end]) <= (
                2 / 32768
            ):
                result[start:end, channel] = True
        count = len(signal) // window
        near = np.abs(signal[: count * window]) >= params.saturation_level
        occupancy = near.reshape(count, window).mean(axis=1)
        result[: count * window, channel] |= (
            np.repeat(occupancy >= params.saturation_occupancy, window) & near
        )
        result[:, channel] |= flat_tops(signal, rate, params.window_ms)
    return result


@pytest.mark.parametrize(
    "source",
    [
        r"aevalsrc=clip(2*sin(2*PI*331*t)\,-1\,1)|-clip(2*sin(2*PI*331*t)\,-1\,1):s=22050:d=0.831",
        r"aevalsrc=if(between(t\,0.1\,0.31)\,0.99995\,0):s=16000:d=0.437",
        "aevalsrc=0.9992+0.0006*t:s=16000:d=0.5",
    ],
)
@pytest.mark.parametrize(
    "params", [ClippingParams(), ClippingParams(saturation_level=1, saturation_occupancy=1)]
)
def test_clipping_chunk_boundaries_match_complete_track_mask(
    make_audio: AudioFactory,
    monkeypatch: pytest.MonkeyPatch,
    source: str,
    params: ClippingParams,
    tmp_path: Path,
) -> None:
    """Plateaus, peak references and occupancy windows retain exact per-sample decisions."""
    file = make_audio(source)
    monkeypatch.setattr(streaming, "BLOCK_SAMPLES", 1024)
    monkeypatch.setattr(clipping_stream, "BLOCK_SAMPLES", 1024)
    rate = probe_file(file).sample_rate
    samples = _decoded(file, rate).astype(np.float32)
    expected = _reference_clipping(samples, rate, params)
    with streaming.audio_buffer(file, rate) as decoded:
        actual = np.concatenate(
            [mask for _, mask in clipping_stream.clipping_blocks(decoded, params)]
        )
    assert actual.shape == expected.shape
    np.testing.assert_array_equal(actual, expected)
    measured = clipping.OPERATOR.run([file], tmp_path, params.model_dump()).files[0]
    assert measured.metadata["audio_metrics"]["clipped_samples"] == int(np.count_nonzero(expected))


def test_decode_keeps_final_partial_block_and_closes_scratch_file(
    make_audio: AudioFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A final short PCM block remains valid and scratch files close on context exit."""
    source = make_audio("sine=sample_rate=16000:duration=0.137")
    monkeypatch.setattr(streaming, "BLOCK_SAMPLES", 257)
    with streaming.audio_buffer(source) as decoded:
        assert decoded.samples == 2192
        assert decoded.read(2000, 2500).shape == (192, 1)
    assert decoded.handle.closed


def test_decode_rejects_partial_pcm_sample(
    make_audio: AudioFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Byte truncation is an error even though a final partial block is allowed."""
    source = make_audio("sine=duration=0.1")
    monkeypatch.setattr(streaming, "stream_tool", lambda *_args, **_kwargs: iter((b"\x00",)))
    with pytest.raises(ExecutionError, match="incomplete PCM sample"):
        list(streaming.channel_blocks(source))


def test_streamed_artifact_keeps_original_pipe_bytes(
    make_audio: AudioFactory, tmp_path: Path
) -> None:
    """Chunking an artifact changes neither its bytes nor content-addressed identity."""
    source = make_audio("sine=sample_rate=16000:duration=0.137")
    args = ["ffmpeg", "-v", "error", "-i", input_path(source), "-f", "wav", "pipe:1"]
    expected = run_tool(args)
    streamed = streaming.stream_artifact(source, tmp_path, args, "test.stream", ActivityParams())
    assert Path(streamed.path).read_bytes() == expected
