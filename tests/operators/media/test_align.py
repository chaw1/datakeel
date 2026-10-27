# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Verify alignment accuracy and conservative handling of ambiguous signals."""

from pathlib import Path

import numpy as np
import pytest
from pydantic import ValidationError as PydanticValidationError

from datakeel.core.errors import ValidationError
from datakeel.core.media_alignment import MediaAlignment
from datakeel.core.models import FileItem
from datakeel.operators.media.align import OPERATOR, AlignParams, estimate_alignment
from datakeel.operators.media.tools import run_tool
from tests.operators.media.helpers import audio_file, shifted_file


@pytest.mark.parametrize("offset_ms", [63, 500, -237])
@pytest.mark.parametrize(
    "source",
    [
        "anoisesrc=sample_rate=16000:duration=3:seed=741",
        "aevalsrc=0.3*sin(2*PI*(170*t+110*t*t)):s=16000:d=3",
    ],
)
def test_alignment_shared_signal_shift_is_within_one_frame(
    tmp_path: Path, offset_ms: int, source: str
) -> None:
    """Recover both timestamp directions for noise and a frequency sweep."""
    reference = audio_file(tmp_path, "reference", source)
    shifted = shifted_file(reference, offset_ms)
    result = OPERATOR.run([reference, shifted], tmp_path / "output")
    measured = MediaAlignment.model_validate(result.files[1].metadata["media_alignment"])
    assert measured.aligned
    assert measured.offset_ms is not None
    assert abs(measured.offset_ms - offset_ms) <= 34
    assert measured.reference_file_id == reference.id
    assert measured.confidence > 0


def test_alignment_three_recordings_remain_relative_to_first(tmp_path: Path) -> None:
    """Avoid compounding offsets by aligning every recording to the first."""
    reference = audio_file(tmp_path, "reference", "anoisesrc=d=3:r=16000:seed=714")
    files = [reference, shifted_file(reference, 500), shifted_file(reference, -120)]
    result = OPERATOR.run(files, tmp_path / "output")
    offsets = [file.metadata["media_alignment"]["offset_ms"] for file in result.files]
    assert offsets == [0.0, 500.0, -120.0]


@pytest.mark.parametrize(
    ("reference_source", "candidate_source", "reason"),
    [
        ("anoisesrc=d=3:r=16000:seed=321", "anoisesrc=d=3:r=16000:seed=123", "no_common_signal"),
        ("anullsrc=r=16000,atrim=duration=3", "anoisesrc=d=3:r=16000:seed=123", "silence"),
        ("sine=f=300:r=16000:d=3", "sine=f=300:r=16000:d=3,adelay=500:all=1", "ambiguous"),
    ],
)
def test_alignment_no_distinct_signal_has_no_offset(
    tmp_path: Path, reference_source: str, candidate_source: str, reason: str
) -> None:
    """Reject unrelated noise, silence and periodic-tone ambiguity."""
    reference = audio_file(tmp_path, "reference", reference_source)
    candidate = audio_file(tmp_path, "candidate", candidate_source)
    result = OPERATOR.run([reference, candidate], tmp_path / "output")
    alignment = MediaAlignment.model_validate(result.files[1].metadata["media_alignment"])
    assert not alignment.aligned
    assert alignment.offset_ms is None
    assert alignment.confidence == 0
    assert alignment.reason == reason


def test_alignment_video_audio_track_matches_audio_recording(tmp_path: Path) -> None:
    """Decode the first audio stream of a video without requiring a separate file."""
    audio = audio_file(tmp_path, "reference", "anoisesrc=d=3:r=16000:seed=15")
    video_path = tmp_path / "camera.mkv"
    run_tool(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=s=64x48:r=30:d=3",
            "-i",
            audio.path,
            "-c:v",
            "ffv1",
            "-c:a",
            "pcm_s16le",
            str(video_path),
        ]
    )
    camera = FileItem(path=str(video_path), filename=video_path.name, modality="video")
    result = OPERATOR.run([camera, shifted_file(audio, 500)], tmp_path / "output")
    assert result.files[1].metadata["media_alignment"]["offset_ms"] == 500


def test_alignment_video_without_audio_is_explicitly_unalignable(tmp_path: Path) -> None:
    """A recording without an audio track must not receive a fabricated lag."""
    path = tmp_path / "silent.mkv"
    run_tool(["ffmpeg", "-y", "-f", "lavfi", "-i", "color=s=64x48:d=1", "-c:v", "ffv1", str(path)])
    video = FileItem(path=str(path), filename=path.name, modality="video")
    audio = audio_file(tmp_path, "audio", "anoisesrc=d=1:r=16000:seed=1")
    result = OPERATOR.run([audio, video], tmp_path / "output")
    assert result.files[1].metadata["media_alignment"]["reason"] == "missing_audio"
    assert result.files[1].metadata["media_alignment"]["offset_ms"] is None


def test_alignment_insufficient_overlap_is_unalignable() -> None:
    """A short fragment cannot satisfy the minimum evidence duration."""
    signal = np.ones(100, dtype=np.float64)
    signal[::2] = -1
    result = estimate_alignment(signal, signal, "reference", AlignParams())
    assert result.reason == "no_common_signal"


def test_alignment_empty_audio_is_unalignable() -> None:
    """Handle an empty decoder result without division or empty-mean warnings."""
    result = estimate_alignment(np.zeros(0), np.zeros(0), "reference", AlignParams())
    assert result.reason == "silence"


def test_alignment_requires_multiple_media_inputs(tmp_path: Path) -> None:
    """Validate the batch modality and cardinality before running a decoder."""
    with pytest.raises(ValidationError, match="at least two"):
        OPERATOR.run([], tmp_path / "output")
    with pytest.raises(ValidationError, match="at least two"):
        OPERATOR.run([FileItem(path="unused", filename="unused")] * 2, tmp_path / "output")
    with pytest.raises(PydanticValidationError):
        OPERATOR.run([], tmp_path / "output", {"unknown": 1})


@pytest.mark.parametrize(
    ("aligned", "offset", "reason"),
    [
        (True, None, "matched"),
        (False, 500.0, "no_common_signal"),
        (True, 500.0, "silence"),
        (False, None, "matched"),
        (True, 500.0, "reference"),
        (True, float("inf"), "matched"),
    ],
)
def test_alignment_model_contradictory_states_are_rejected(
    *, aligned: bool, offset: float | None, reason: str
) -> None:
    """Keep serialized synchronization boundaries consistent and finite."""
    with pytest.raises(PydanticValidationError):
        MediaAlignment.model_validate(
            {
                "reference_file_id": "reference",
                "aligned": aligned,
                "offset_ms": offset,
                "reason": reason,
            }
        )


def test_alignment_antiphase_stereo_preserves_shared_signal(tmp_path: Path) -> None:
    """Select a real channel so opposite stereo phases cannot cancel alignment evidence."""
    reference = audio_file(
        tmp_path,
        "stereo-reference",
        "aevalsrc=0.4*sin(2*PI*(100*t+150*t*t))|-0.4*sin(2*PI*(100*t+150*t*t)):s=16000:d=3",
    )
    result = OPERATOR.run([reference, shifted_file(reference, 500)], tmp_path / "output")
    alignment = MediaAlignment.model_validate(result.files[1].metadata["media_alignment"])
    assert alignment.aligned
    assert alignment.offset_ms == 500


def test_alignment_low_frequency_noise_with_gain_and_hiss_is_confident(tmp_path: Path) -> None:
    """A wind-like shared signal keeps a sharp, confident peak despite gain and hiss."""
    reference = audio_file(
        tmp_path, "reference", "anoisesrc=color=brown:r=16000:d=4:amplitude=0.4:seed=58"
    )
    hiss = audio_file(tmp_path, "hiss", "anoisesrc=color=white:r=16000:d=5:amplitude=0.01:seed=91")
    path = tmp_path / "microphone.wav"
    run_tool(
        [
            "ffmpeg",
            "-y",
            "-i",
            reference.path,
            "-i",
            hiss.path,
            "-filter_complex",
            "[0:a]adelay=730:all=1,volume=0.5[d];[d][1:a]amix=inputs=2:normalize=0:duration=first",
            "-c:a",
            "pcm_s16le",
            str(path),
        ]
    )
    microphone = FileItem(id="microphone", path=str(path), filename=path.name, modality="audio")
    result = OPERATOR.run([reference, microphone], tmp_path / "output")
    alignment = MediaAlignment.model_validate(result.files[1].metadata["media_alignment"])
    assert alignment.offset_ms is not None
    assert abs(alignment.offset_ms - 730) <= 34
    assert alignment.confidence >= 0.7


def test_alignment_dominant_hum_does_not_hide_the_shared_lag(tmp_path: Path) -> None:
    """A loud shared mains hum is periodic; the broadband part still fixes the lag."""
    reference = audio_file(
        tmp_path,
        "reference",
        "aevalsrc=0.5*sin(2*PI*60*t):s=16000:d=4[h];"
        "anoisesrc=color=white:r=16000:d=4:amplitude=0.05:seed=12[n];"
        "[h][n]amix=inputs=2:normalize=0",
    )
    delayed = shifted_file(reference, 730)
    result = OPERATOR.run([reference, delayed], tmp_path / "output")
    alignment = MediaAlignment.model_validate(result.files[1].metadata["media_alignment"])
    assert alignment.aligned
    assert alignment.offset_ms is not None
    assert abs(alignment.offset_ms - 730) <= 34
