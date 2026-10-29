# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Clipping survives lossy coding as dwelling near full scale; loud clean audio does not."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from datakeel.core.models import FileItem
from datakeel.operators.audio import clipping
from datakeel.operators.media.tools import run_tool

if TYPE_CHECKING:
    from pathlib import Path

# lavfi's sine has amplitude 1/8, so a gain of 8 reaches full scale.
_CLIPPED = (
    "volume='if(between(t,1,3),16,4)':eval=frame,"
    "aformat=sample_fmts=flt,asoftclip=type=hard:threshold=1"
)


def _aac(directory: Path, name: str, source: str, filters: str) -> FileItem:
    path = directory / f"{name}.m4a"
    run_tool(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            source,
            "-af",
            filters,
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            str(path),
        ]
    )
    return FileItem(id=name, path=str(path), filename=path.name, modality="audio")


def _clipped_ms(file: FileItem, directory: Path) -> list[tuple[int, int]]:
    measured = clipping.OPERATOR.run([file], directory / "out").files[0]
    return [
        (issue["start_ms"], issue["end_ms"])
        for issue in measured.metadata["media_issues"]
        if issue["code"] == "audio_clipping"
    ]


@pytest.mark.parametrize("frequency", [100, 1000, 3000])
def test_aac_coded_hard_clipping_is_found_where_it_happens(tmp_path: Path, frequency: int) -> None:
    """Seconds 1-3 are clipped at double full scale; at least 90% of them is reported."""
    source = f"sine=frequency={frequency}:sample_rate=44100:duration=4"
    spans = _clipped_ms(_aac(tmp_path, f"clipped-{frequency}", source, _CLIPPED), tmp_path)
    inside = sum(max(0, min(end, 3000) - max(start, 1000)) for start, end in spans)
    outside = sum(end - start for start, end in spans) - inside
    assert inside >= 0.9 * 2000
    assert outside <= 50


@pytest.mark.parametrize(
    ("name", "source", "filters"),
    [
        ("full-scale-sine", "sine=frequency=440:sample_rate=44100:duration=3", "volume=7.92"),
        ("low-sine", "sine=frequency=100:sample_rate=44100:duration=3", "volume=7.2"),
        (
            "loud-noise",
            "anoisesrc=color=pink:sample_rate=44100:duration=3:amplitude=1:seed=3",
            "loudnorm=I=-9:TP=-0.3",
        ),
    ],
)
def test_loud_unclipped_aac_is_not_clipping(
    tmp_path: Path, name: str, source: str, filters: str
) -> None:
    """Decoder overshoot above full scale moves; only a flat or dwelling ceiling is clipping."""
    assert _clipped_ms(_aac(tmp_path, name, source, filters), tmp_path) == []
