# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Clipped voice keeps flat-topped peaks through lossy coding; clean and limited voice does not."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
import pytest

from datakeel.core.models import FileItem
from datakeel.operators.audio import clipping
from datakeel.operators.audio import flat_tops as flat_tops_module
from datakeel.operators.audio.flat_tops import flat_tops
from datakeel.operators.media.tools import run_tool

if TYPE_CHECKING:
    from pathlib import Path

    from numpy.typing import NDArray

_RATE = 44100
_CODECS = {"mp3": "libmp3lame", "m4a": "aac", "opus": "libopus"}
_LIMITER = "alimiter=limit=0.95:attack=5:release=50:level=disabled"
_COMPRESSOR = (
    "acompressor=threshold=0.1:ratio=8:attack=1:release=50:makeup=4,"
    "alimiter=limit=0.97:level=disabled"
)
_LOUD_NOISE = "anoisesrc=color=white:sample_rate=44100:duration=4:amplitude=0.1:seed=5"


def _voice(seconds: float = 4.0) -> NDArray[np.float64]:
    """Return syllables of a vowel: every glottal pulse rings at three formants."""
    t = np.arange(int(0.012 * _RATE)) / _RATE
    ring = sum(
        gain * np.exp(-np.pi * bandwidth * t) * np.sin(2 * np.pi * formant * t)
        for formant, bandwidth, gain in ((700, 80, 1.0), (1200, 100, 0.5), (2500, 150, 0.25))
    )
    signal = np.zeros(int(seconds * _RATE) + len(t))
    time = 0.0
    while time < seconds:
        syllable = time % 0.33 / 0.25
        if syllable < 1:
            start = int(time * _RATE)
            signal[start : start + len(t)] += ring * np.sin(np.pi * syllable) ** 0.6
        time += 1 / (140 * (1 + 0.1 * np.sin(2 * np.pi * 0.7 * time)))
    signal = signal[: int(seconds * _RATE)]
    return signal / np.abs(signal).max()


def _encode(
    directory: Path,
    name: str,
    signal: NDArray[np.float64],
    extension: str,
    filters: str = "anull",
) -> FileItem:
    raw = directory / f"{name}.f32"
    raw.write_bytes(signal.astype("<f4").tobytes())
    source = ["-f", "f32le", "-ar", str(_RATE), "-ac", "1", "-i", str(raw)]
    return _coded(directory, name, source, filters, extension)


def _coded(directory: Path, name: str, source: list[str], filters: str, extension: str) -> FileItem:
    path = directory / f"{name}.{extension}"
    codec = ["-af", filters, "-c:a", _CODECS[extension], "-b:a", "128k"]
    run_tool(["ffmpeg", "-y", *source, *codec, str(path)])
    return FileItem(id=name, path=str(path), filename=path.name, modality="audio")


def _clipped_ms(file: FileItem, directory: Path) -> list[tuple[int, int]]:
    measured = clipping.OPERATOR.run([file], directory / "out").files[0]
    return [
        (issue["start_ms"], issue["end_ms"])
        for issue in measured.metadata["media_issues"]
        if issue["code"] == "audio_clipping"
    ]


@pytest.mark.parametrize("extension", list(_CODECS))
def test_lossy_coded_clipped_voice_is_found_in_every_syllable(
    tmp_path: Path, extension: str
) -> None:
    """Seconds 1-3 are driven 12 dB into a hard clip; each of their six syllables is found."""
    voice = _voice()
    drive = np.full(len(voice), 0.8)
    drive[_RATE : 3 * _RATE] = 4.0
    clipped = _encode(tmp_path, "clipped", np.clip(voice * drive, -1, 1), extension)
    spans = _clipped_ms(clipped, tmp_path)
    inside = sum(max(0, min(end, 3000) - max(start, 1000)) for start, end in spans)
    assert len(spans) >= 5
    assert inside >= 800
    assert sum(end - start for start, end in spans) - inside <= 50


@pytest.mark.parametrize("extension", list(_CODECS))
def test_lossy_coded_clean_and_limited_voice_is_not_clipping(
    tmp_path: Path, extension: str
) -> None:
    """A limiter reaches the ceiling as often as clipping does, but its peaks stay rounded."""
    voice = _voice()
    assert _clipped_ms(_encode(tmp_path, "clean", voice * 0.95, extension), tmp_path) == []
    limited = _encode(tmp_path, "limited", voice * 3, extension, _LIMITER)
    assert _clipped_ms(limited, tmp_path) == []


@pytest.mark.parametrize("extension", list(_CODECS))
def test_lossy_coded_compressed_voice_and_loud_noise_are_not_clipping(
    tmp_path: Path, extension: str
) -> None:
    """Coding ripple makes rounded peaks look flat sample by sample, not over 0.25 ms."""
    compressed = _encode(tmp_path, "compressed", _voice() * 2, extension, _COMPRESSOR)
    assert _clipped_ms(compressed, tmp_path) == []
    source = ["-f", "lavfi", "-i", _LOUD_NOISE]
    noise = _coded(tmp_path, "noise", source, "lowpass=f=8000,loudnorm=I=-9:TP=-0.3", extension)
    assert _clipped_ms(noise, tmp_path) == []


def _tone(level: float, ceiling: float) -> NDArray[np.float32]:
    t = np.arange(_RATE) / _RATE
    return np.clip(level * np.sin(2 * np.pi * 300 * t), -ceiling, ceiling).astype(np.float32)


def test_flat_tops_need_a_flat_shape_near_the_peak_level() -> None:
    """A tone clipped 6 dB below full scale is found; the same tone unclipped is rounded."""
    assert flat_tops(_tone(1.0, 0.5), _RATE, 20).mean() > 0.3
    assert not flat_tops(_tone(1.0, 1.0), _RATE, 20).any()
    quiet = _tone(1.0, 0.5) * np.where(np.arange(_RATE) < _RATE // 2, 0.5, 1).astype(np.float32)
    flagged = flat_tops(quiet, _RATE, 20)
    assert not flagged[: _RATE // 2].any()
    assert flagged[_RATE // 2 :].any()


def _with_clipped_cycles(seconds: tuple[float, ...], cycles: int) -> NDArray[np.float32]:
    """Clip whole 300 Hz cycles 6 dB deep, then restore their peak to the tone's level."""
    tone = _tone(0.5, 1.0)
    for second in seconds:
        start = int(second * _RATE)
        stop = start + cycles * _RATE // 300
        tone[start:stop] = np.clip(tone[start:stop], -0.25, 0.25) * 2
    return tone


def test_isolated_flat_tops_are_not_a_clipped_passage() -> None:
    """One clipped cycle gives two flat tops, fewer than four in a window and its neighbours."""
    assert not flat_tops(_with_clipped_cycles((0.2, 0.5, 0.8), 1), _RATE, 20).any()
    assert flat_tops(_with_clipped_cycles((0.5,), 3), _RATE, 20).any()


def test_blocks_give_the_same_flags_as_one_pass(monkeypatch: pytest.MonkeyPatch) -> None:
    """Blocks end where the smoothed signal changes sign and are smoothed with their neighbours."""
    voice = np.clip(_voice(2.0) * 4, -1, 1).astype(np.float32)
    whole = flat_tops(voice, _RATE, 20)
    monkeypatch.setattr(flat_tops_module, "_BLOCK", 997)
    assert whole.any()
    assert np.array_equal(flat_tops(voice, _RATE, 20), whole)
    assert not flat_tops(np.zeros(0, dtype=np.float32), _RATE, 20).any()
