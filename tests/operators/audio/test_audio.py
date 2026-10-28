# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Signal-level regressions for audio probing, activity, trimming and clipping."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import pytest

from datakeel.core.media_models import MediaProbe
from datakeel.operators.audio import clipping, probe, trim_silence, vad
from datakeel.operators.audio.common import activity, activity_metrics, runs
from datakeel.operators.audio.params import ActivityParams
from datakeel.operators.media.tools import probe_file
from tests.operators.media.helpers import failure_reason

if TYPE_CHECKING:
    from datakeel.operators.base import Operator
    from tests.operators.audio.conftest import AudioFactory


def test_probe_reads_actual_audio_properties(make_audio: AudioFactory, tmp_path: Path) -> None:
    """Ignore stale metadata and expose the source PCM stream properties."""
    source = make_audio("sine=frequency=527:sample_rate=22050:duration=1.2")
    source.metadata["media_probe"] = {"duration_ms": 90000}
    result = probe.OPERATOR.run([source], tmp_path / "probe")
    measured = result.files[0].metadata["media_probe"]
    assert measured["duration_ms"] == 1200
    assert measured["sample_rate"] == 22050
    assert measured["channels"] == measured["audio_tracks"] == 1
    assert measured["codec"] == "pcm_s16le"
    assert source.metadata["media_probe"] == {"duration_ms": 90000}


def test_probe_rejects_undecodable_audio(make_audio: AudioFactory, tmp_path: Path) -> None:
    """Report malformed content rather than returning fabricated measurements."""
    source = make_audio("anullsrc=r=16000:cl=mono:d=0.1")
    Path(source.path).write_bytes(b"invalid recording")
    result = probe.OPERATOR.run([source], tmp_path / "probe")
    assert "could not process recording" in failure_reason(result.files[0], "audio.probe")
    assert result.quality["failed_files"] == [source.id]


def test_vad_locates_energy_and_silence(make_audio: AudioFactory, tmp_path: Path) -> None:
    """Locate activity boundaries within one 20 ms RMS frame."""
    source = make_audio(
        "sine=frequency=731:sample_rate=16000:duration=1",
        "adelay=500,apad=pad_dur=0.4",
    )
    measured = vad.OPERATOR.run([source], tmp_path / "vad").files[0]
    metrics = measured.metadata["audio_metrics"]
    assert metrics["vad_method"] == "energy_activity_estimate_not_speech_recognition"
    assert [(span["start_ms"], span["end_ms"]) for span in metrics["vad_intervals"]] == [
        (500, 1500)
    ]
    assert metrics["silence_ratio"] == pytest.approx(900 / 1900, abs=1e-6)
    assert [span["code"] for span in measured.metadata["media_issues"]] == [
        "audio_silence",
        "audio_silence",
    ]


def test_vad_distinguishes_quiet_signal_with_configurable_threshold(
    make_audio: AudioFactory, tmp_path: Path
) -> None:
    """Honor the dBFS threshold instead of treating every nonzero sample as activity."""
    source = make_audio("sine=frequency=777:sample_rate=16000:duration=0.5", "volume=0.01")
    default = vad.OPERATOR.run([source], tmp_path / "default").files[0]
    sensitive = vad.OPERATOR.run(
        [source], tmp_path / "sensitive", {"threshold_dbfs": -70.0, "frame_ms": 25}
    ).files[0]
    assert default.metadata["audio_metrics"]["active_ratio"] == 0
    assert sensitive.metadata["audio_metrics"]["active_ratio"] == 1


def test_vad_hysteresis_removes_transients_and_bridges_short_gaps(
    make_audio: AudioFactory, tmp_path: Path
) -> None:
    """Use interval durations rather than fixture-specific sample values."""
    source = make_audio(r"aevalsrc=if(between(t\,0.2\,0.24)\,0\,0.2*sin(2*PI*619*t)):s=16000:d=0.5")
    measured = vad.OPERATOR.run([source], tmp_path / "gap").files[0]
    assert len(measured.metadata["audio_metrics"]["vad_intervals"]) == 1
    separated = vad.OPERATOR.run([source], tmp_path / "split", {"min_silence_ms": 20}).files[0]
    assert len(separated.metadata["audio_metrics"]["vad_intervals"]) == 2
    transient = make_audio("sine=frequency=619:sample_rate=16000:duration=0.04")
    result = vad.OPERATOR.run([transient], tmp_path / "transient").files[0]
    assert result.metadata["audio_metrics"]["vad_intervals"] == []


def test_probe_rejects_missing_audio_stream(
    make_audio: AudioFactory, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A file without any audio track must not pass an audio-specific probe."""
    source = make_audio("sine=duration=0.2")
    monkeypatch.setattr(probe, "probe_file", lambda _file: MediaProbe(duration_ms=200))
    result = probe.OPERATOR.run([source], tmp_path / "missing")
    assert "decodable audio stream" in failure_reason(result.files[0], "audio.probe")


def test_vad_and_trim_keep_opposite_phase_stereo(make_audio: AudioFactory, tmp_path: Path) -> None:
    """Prevent active stereo recordings from disappearing after a cancelling downmix."""
    source = make_audio("aevalsrc=0.2*sin(2*PI*557*t)|-0.2*sin(2*PI*557*t):s=16000:d=0.5")
    measured = vad.OPERATOR.run([source], tmp_path / "vad").files[0]
    assert measured.metadata["audio_metrics"]["active_ratio"] == 1
    trimmed = trim_silence.OPERATOR.run([measured], tmp_path / "trim").files[0]
    assert trimmed.metadata["media_probe"]["duration_ms"] == 500
    assert trimmed.metadata["media_probe"]["channels"] == 2


def test_activity_handles_empty_and_partial_frames() -> None:
    """Avoid invented duration for empty inputs and cap final partial-frame bounds."""
    empty = activity(np.array([], dtype=np.float64), ActivityParams())
    assert empty.duration_ms == 0
    assert activity_metrics(empty).active_ratio == 0
    assert runs(np.array([True, True, False, True], dtype=np.bool_)) == [(0, 2), (3, 4)]
    partial = activity(np.ones(1680, dtype=np.float64), ActivityParams())
    assert partial.active[-1].end_ms == partial.duration_ms == 105


def test_trim_preserves_source_timing_and_deterministic_artifacts(
    make_audio: AudioFactory, tmp_path: Path
) -> None:
    """Trim edge silence, retain internal silence and freeze immediate provenance."""
    source = make_audio(
        "sine=frequency=523:sample_rate=16000:duration=1",
        "adelay=500,apad=pad_dur=0.4",
    )
    original = Path(source.path).read_bytes()
    result = trim_silence.OPERATOR.run([source], tmp_path / "first", {"padding_ms": 0})
    again = trim_silence.OPERATOR.run([source], tmp_path / "second", {"padding_ms": 0})
    trimmed = result.files[0]
    assert trimmed.id == again.files[0].id
    assert trimmed.sha256 == again.files[0].sha256
    assert probe_file(trimmed).duration_ms == 1000
    assert (trimmed.metadata["start_ms"], trimmed.metadata["end_ms"]) == (500, 1500)
    assert trimmed.metadata["source_file_id"] == source.id
    history = trimmed.metadata["media_history"][-1]
    assert history["operator"] == "audio.trim_silence"
    assert history["version"] == "1.0.0"
    assert history["parameters"]["padding_ms"] == 0
    assert len(history["parameters_digest"]) == 64
    assert trimmed.metadata["audio_metrics"]["active_ratio"] == 1
    assert Path(source.path).read_bytes() == original


def test_trim_padding_and_all_silence(make_audio: AudioFactory, tmp_path: Path) -> None:
    """Retain requested context and remove recordings with no detected activity."""
    source = make_audio(
        "sine=frequency=523:sample_rate=16000:duration=0.6", "adelay=300,apad=pad_dur=0.3"
    )
    trimmed = trim_silence.OPERATOR.run([source], tmp_path / "trim").files[0]
    assert probe_file(trimmed).duration_ms == 640
    silent = make_audio("anullsrc=r=16000:cl=mono:d=0.5")
    result = trim_silence.OPERATOR.run([silent], tmp_path / "silent")
    assert result.files == []
    assert result.quality["removed_count"] == 1


def test_clipping_detects_plateaus_in_opposite_phase_stereo(
    make_audio: AudioFactory, tmp_path: Path
) -> None:
    """Measure every channel so opposite phases cannot hide digital clipping."""
    source = make_audio(
        r"aevalsrc=clip(2*sin(2*PI*440*t)\,-1\,1)|-clip(2*sin(2*PI*440*t)\,-1\,1):s=16000:d=0.2"
    )
    measured = clipping.OPERATOR.run([source], tmp_path / "clip").files[0]
    assert measured.metadata["audio_metrics"]["clipping_ratio"] > 0.6
    assert measured.metadata["audio_metrics"]["clipped_samples"] > 3000
    assert measured.metadata["media_issues"][0]["code"] == "audio_clipping"
    assert all(
        0 <= span["start_ms"] < span["end_ms"] <= 200 for span in measured.metadata["media_issues"]
    )


def test_clipping_refresh_removes_stale_intervals(make_audio: AudioFactory, tmp_path: Path) -> None:
    """A rerun with a higher threshold must clear previous clipping deductions."""
    source = make_audio("sine=frequency=523:sample_rate=16000:duration=0.3")
    low = clipping.OPERATOR.run(
        [source], tmp_path / "low", {"saturation_level": 0.1, "saturation_occupancy": 0.1}
    ).files[0]
    refreshed = clipping.OPERATOR.run([low], tmp_path / "normal").files[0]
    assert low.metadata["audio_metrics"]["clipping_ratio"] > 0
    assert refreshed.metadata["audio_metrics"]["clipping_ratio"] == 0
    assert refreshed.metadata["media_issues"] == []


@pytest.mark.parametrize(
    "operator", [probe.OPERATOR, vad.OPERATOR, clipping.OPERATOR, trim_silence.OPERATOR]
)
def test_audio_operators_reject_undeclared_parameters(operator: Operator, tmp_path: Path) -> None:
    """Expose strict parameter schemas at every operator boundary."""
    with pytest.raises(ValueError, match="Extra inputs"):
        operator.run([], tmp_path / "invalid", {"undeclared": 1})
