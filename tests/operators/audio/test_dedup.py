# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""MFCC deduplication regressions use only locally synthesized recordings."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
import pytest

from datakeel.core.models import FileItem
from datakeel.operators.audio.dedup import OPERATOR
from datakeel.operators.audio.fingerprint import fingerprint, shape_similarity, signature
from datakeel.operators.media.tools import run_tool

if TYPE_CHECKING:
    from pathlib import Path

    from tests.operators.audio.conftest import AudioFactory


def test_dedup_matches_gain_changes_and_preserves_different_frequency(
    make_audio: AudioFactory, tmp_path: Path
) -> None:
    """MFCC excludes absolute gain while retaining frequency identity."""
    first = make_audio("sine=frequency=440:sample_rate=16000:duration=1")
    quieter = make_audio("sine=frequency=440:sample_rate=16000:duration=1", "volume=0.6")
    distinct = make_audio("sine=frequency=880:sample_rate=16000:duration=1")
    result = OPERATOR.run([first, quieter, distinct], tmp_path / "dedup")
    assert [file.id for file in result.files] == [first.id, distinct.id]
    assert result.quality["removed_count"] == 1
    assert result.quality["issues"][0]["duplicate_of"] == first.id
    assert result.files[0].metadata["audio_metrics"]["fingerprint_method"] == "temporal_mfcc_v2"
    assert len(result.files[0].metadata["audio_metrics"]["fingerprint"]) == 64 * 13


@pytest.mark.parametrize(
    ("color", "filters"),
    [
        ("white", "anull"),
        ("pink", "anull"),
        ("brown", "anull"),
        ("blue", "anull"),
        ("violet", "anull"),
        ("pink", "lowpass=f=20:p=2"),
        ("white", "bandpass=f=600:width_type=h:width=1"),
    ],
)
def test_dedup_preserves_unrelated_noise_and_duration(
    make_audio: AudioFactory, tmp_path: Path, color: str, filters: str
) -> None:
    """Time-ordered features must distinguish independently generated noise."""
    source = f"anoisesrc=color={color}:sample_rate=16000:duration=3"
    first = make_audio(source + ":seed=17", filters)
    different = make_audio(source + ":seed=29", filters)
    shorter = make_audio(f"anoisesrc=color={color}:sample_rate=16000:duration=0.5:seed=17", filters)
    duplicate = make_audio(source + ":seed=17", filters)
    result = OPERATOR.run([first, different, shorter, duplicate], tmp_path / "dedup")
    assert [file.id for file in result.files] == [first.id, different.id, shorter.id]


def test_dedup_can_mark_without_removing_and_avoids_stale_source_mutation(
    make_audio: AudioFactory, tmp_path: Path
) -> None:
    """Keep source IDs and expose which retained recording matched a duplicate."""
    first = make_audio("sine=frequency=631:sample_rate=16000:duration=0.5")
    second = make_audio("sine=frequency=631:sample_rate=16000:duration=0.5")
    result = OPERATOR.run([first, second], tmp_path / "mark", {"remove": False})
    assert len(result.files) == 2
    assert result.files[1].metadata["audio_metrics"]["duplicate_of"] == first.id
    assert first.metadata == second.metadata == {}
    refreshed = OPERATOR.run([result.files[1]], tmp_path / "refresh").files[0]
    assert "duplicate_of" not in refreshed.metadata["audio_metrics"]


def test_dedup_distinguishes_stereo_tone_from_digital_silence(
    make_audio: AudioFactory, tmp_path: Path
) -> None:
    """Do not collapse opposite-phase stereo and real silence into one fingerprint."""
    tone = make_audio("aevalsrc=0.2*sin(2*PI*631*t)|-0.2*sin(2*PI*631*t):s=16000:d=0.5")
    silence = make_audio("anullsrc=r=16000:cl=stereo:d=0.5")
    assert len(OPERATOR.run([tone, silence], tmp_path / "stereo").files) == 2


def test_fingerprint_handles_short_and_empty_audio() -> None:
    """Avoid invalid FFT shapes for edge cases and return finite deterministic output."""
    empty = signature(np.array([], dtype=np.float64))
    short = signature(np.zeros(4, dtype=np.float64))
    assert empty.duration_ms == 0
    assert np.isfinite(fingerprint(empty).coefficients).all()
    assert len(fingerprint(short).coefficients) == 64 * 13
    assert shape_similarity(empty, short) == 1


def test_dedup_rejects_unknown_and_invalid_parameters(tmp_path: Path) -> None:
    """Validate strict schemas before reading audio files."""
    for parameters in ({"typo": True}, {"correlation_threshold": 1.01}):
        with pytest.raises(ValueError, match="validation error"):
            OPERATOR.run([], tmp_path / "invalid", parameters)


@pytest.mark.parametrize(
    ("codec", "extension"), [("libmp3lame", "mp3"), ("aac", "m4a"), ("libopus", "opus")]
)
@pytest.mark.parametrize("color", ["brown", "pink", "violet"])
def test_dedup_lossy_copy_is_duplicate_but_independent_take_is_not(
    make_audio: AudioFactory, tmp_path: Path, codec: str, extension: str, color: str
) -> None:
    """A re-encoded copy keeps its fluctuations; an independent take of the same noise does not."""
    source = f"anoisesrc=color={color}:sample_rate=48000:duration=3:amplitude=0.3"
    original = make_audio(source + ":seed=17")
    independent = make_audio(source + ":seed=29")
    path = tmp_path / f"copy.{extension}"
    run_tool(["ffmpeg", "-y", "-i", original.path, "-c:a", codec, "-b:a", "96k", str(path)])
    copy = FileItem(id="copy", path=str(path), filename=path.name, modality="audio")
    result = OPERATOR.run([original, independent, copy], tmp_path / "lossy", {"remove": False})
    assert [file.metadata["audio_metrics"].get("duplicate_of") for file in result.files] == [
        None,
        None,
        original.id,
    ]
