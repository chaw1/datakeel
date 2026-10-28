# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Generated EBU R128 measurement and optional normalization regressions."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from datakeel.operators.audio import loudness
from datakeel.operators.audio.loudness import OPERATOR
from tests.operators.media.helpers import failure_reason

if TYPE_CHECKING:
    from tests.operators.audio.conftest import AudioFactory


def test_loudness_measures_and_normalizes_actual_output(
    make_audio: AudioFactory, tmp_path: Path
) -> None:
    """Bring a quiet signal to the configured LUFS target and remeasure its output."""
    source = make_audio("sine=frequency=997:sample_rate=48000:duration=2", "volume=0.1")
    original = Path(source.path).read_bytes()
    measured = OPERATOR.run([source], tmp_path / "measure").files[0]
    metrics = measured.metadata["audio_metrics"]
    assert metrics["integrated_lufs"] < -40
    assert metrics["loudness_measurable"] is True
    assert measured.metadata["media_issues"][0]["code"] == "audio_loudness"
    normalized = OPERATOR.run([measured], tmp_path / "normalize", {"normalize": True}).files[0]
    actual = normalized.metadata["audio_metrics"]
    assert actual["integrated_lufs"] == pytest.approx(-23.0, abs=0.2)
    assert actual["true_peak_dbfs"] <= -1
    assert actual["loudness_deviation_lu"] <= 0.2
    assert normalized.metadata["media_issues"] == []
    assert normalized.metadata["source_file_id"] == source.id
    assert normalized.metadata["media_probe"]["sample_rate"] == 48000
    assert Path(source.path).read_bytes() == original


def test_loudness_normalization_is_deterministic(make_audio: AudioFactory, tmp_path: Path) -> None:
    """Repeat identical parameters without changing artifact identity or bytes."""
    source = make_audio("sine=frequency=631:sample_rate=16000:duration=1")
    first = OPERATOR.run([source], tmp_path / "first", {"normalize": True}).files[0]
    second = OPERATOR.run([source], tmp_path / "second", {"normalize": True}).files[0]
    assert (first.id, first.sha256) == (second.id, second.sha256)
    assert first.metadata["media_history"][0]["end_ms"] == 1000


def test_loudness_silence_reports_unmeasurable_without_nan(
    make_audio: AudioFactory, tmp_path: Path
) -> None:
    """Represent digital silence explicitly instead of persisting non-finite numbers."""
    source = make_audio("anullsrc=r=16000:cl=mono:d=1")
    measured = OPERATOR.run([source], tmp_path / "silence", {"normalize": True}).files[0]
    assert measured.id == source.id
    assert measured.metadata["audio_metrics"]["loudness_measurable"] is False
    assert "integrated_lufs" not in measured.metadata["audio_metrics"]
    assert "NaN" not in measured.model_dump_json()
    assert "Infinity" not in measured.model_dump_json()


def test_loudness_rejects_undeclared_and_out_of_range_parameters(tmp_path: Path) -> None:
    """Validate target limits and strict booleans before starting an external tool."""
    for parameters in ({"typo": True}, {"target_lufs": 0.0}, {"normalize": 1}):
        with pytest.raises(ValueError, match="validation error"):
            OPERATOR.run([], tmp_path / "invalid", parameters)


def test_loudness_reports_missing_measurement_json(
    make_audio: AudioFactory, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fail clearly when a tool omits its promised measurement result."""
    source = make_audio("sine=duration=0.5")
    monkeypatch.setattr(
        loudness, "run_tool_stderr", lambda _arguments, **_options: b"no measurement"
    )
    failed = OPERATOR.run([source], tmp_path / "missing").files[0]
    assert "EBU R128 loudness measurements" in failure_reason(failed, "audio.loudness")
