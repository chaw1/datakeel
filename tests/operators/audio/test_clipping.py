# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Clipping survives lossy coding and is reported once per distorted passage."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from datakeel.core.models import FileItem
from datakeel.operators.audio import clipping
from datakeel.operators.media.tools import run_tool

if TYPE_CHECKING:
    from pathlib import Path

    from tests.operators.audio.conftest import AudioFactory

_BOOSTED = "volume='if(between(t,1,2),24,4)':eval=frame"


def _spans(file: FileItem) -> list[tuple[int, int]]:
    return [(item["start_ms"], item["end_ms"]) for item in file.metadata["media_issues"]]


def test_clipping_one_passage_is_one_interval(make_audio: AudioFactory, tmp_path: Path) -> None:
    """Hundreds of per-cycle plateaus merge into the single boosted passage."""
    source = make_audio("sine=frequency=330:sample_rate=44100:duration=3", _BOOSTED)
    measured = clipping.OPERATOR.run([source], tmp_path / "clip").files[0]
    [(start_ms, end_ms)] = _spans(measured)
    assert abs(start_ms - 1000) <= 30
    assert abs(end_ms - 2000) <= 30


def test_clipping_survives_lossy_coding(make_audio: AudioFactory, tmp_path: Path) -> None:
    """AAC turns flat tops into ringing below full scale; the dwelling is still found."""
    source = make_audio("sine=frequency=330:sample_rate=44100:duration=3", _BOOSTED)
    path = tmp_path / "coded.m4a"
    run_tool(["ffmpeg", "-y", "-i", source.path, "-c:a", "aac", "-b:a", "128k", str(path)])
    coded = FileItem(id="coded", path=str(path), filename=path.name, modality="audio")
    measured = clipping.OPERATOR.run([coded], tmp_path / "coded").files[0]
    [(start_ms, end_ms)] = _spans(measured)
    assert abs(start_ms - 1000) <= 50
    assert abs(end_ms - 2000) <= 50


@pytest.mark.parametrize(
    ("source", "filters"),
    [
        ("sine=frequency=330:sample_rate=44100:duration=2", "volume=7.9"),
        ("anoisesrc=color=pink:sample_rate=44100:duration=2:amplitude=0.45:seed=5", "anull"),
    ],
)
def test_clipping_loud_unclipped_signals_are_clean(
    make_audio: AudioFactory, tmp_path: Path, source: str, filters: str
) -> None:
    """A near-full-scale sine and loud noise never dwell at full scale like a clipped signal."""
    measured = clipping.OPERATOR.run([make_audio(source, filters)], tmp_path / "clean").files[0]
    assert measured.metadata["media_issues"] == []
    assert measured.metadata["audio_metrics"]["clipping_ratio"] == 0
