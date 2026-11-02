# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Generate deterministic local audio/video fixtures and attach real ffprobe measurements."""

import wave
from pathlib import Path
from typing import TYPE_CHECKING

from datakeel.core.annotation_models import AnnotationRecord
from datakeel.core.models import FileItem
from datakeel.operators.media.command import run_tool
from datakeel.operators.media.tools import probe_file
from datakeel.storage.database import Database, VersionRow

if TYPE_CHECKING:
    from pydantic import JsonValue

_RATE = 16_000
_WAV_DURATION_MS = 3250
_SHORT_VIDEO_LIMIT_MS = 60_000
_LONG_MEDIA_MS = 7_200_000


def _wav(path: Path, duration_ms: int, index: int) -> None:
    frames = round(_RATE * duration_ms / 1000)
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(_RATE)
        output.writeframes(bytes([index % 256, 0]) * frames)


def _video(path: Path, duration_ms: int) -> None:
    frame_rate = 30 if duration_ms < _SHORT_VIDEO_LIMIT_MS else 1
    run_tool(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c=blue:s=64x64:r={frame_rate}:d={duration_ms / 1000}",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(path.absolute()),
        ],
        timeout=120,
    )


def segment_sources(directory: Path, duration_ms: int, count: int) -> list[Path]:
    """Create short WAV, browser-decodable MP4 or a two-hour low-bitrate video."""
    directory.mkdir(parents=True, exist_ok=True)
    result: list[Path] = []
    for index in range(count):
        video = duration_ms != _WAV_DURATION_MS
        path = directory / f"sample-{index:03d}.{'mp4' if video else 'wav'}"
        if video:
            _video(path, duration_ms)
        else:
            _wav(path, duration_ms, index)
        result.append(path)
    return result


def segment_annotation(sample_id: str, duration_ms: int) -> AnnotationRecord:
    """Build reviewed overlap/nesting fixtures or five hundred long-media segments."""
    segments = (
        [
            {
                "category": "cat" if index % 2 == 0 else "dog",
                "start_ms": index * 14_400,
                "end_ms": index * 14_400 + 1000,
                "attributes": {"note": f"段 {index}"},
            }
            for index in range(500)
        ]
        if duration_ms == _LONG_MEDIA_MS
        else [
            {"category": "cat", "start_ms": 0, "end_ms": 1000, "attributes": {"note": "开始"}},
            {
                "category": "dog",
                "start_ms": 500,
                "end_ms": min(2000, duration_ms),
                "attributes": {"note": "重叠"},
            },
            {
                "category": "cat",
                "start_ms": 1000,
                "end_ms": duration_ms,
                "attributes": {"note": "结束"},
            },
        ]
    )
    return AnnotationRecord.model_validate(
        {
            "sample_id": sample_id,
            "annotator_id": "local",
            "segments": segments,
            "media_duration_ms": duration_ms,
        }
    )


def probe_sources(db: Database, version_id: str) -> dict[str, int]:
    """Write actual readable media facts and return their duration by sample identity."""
    durations: dict[str, int] = {}
    with db.session() as session:
        version = session.get(VersionRow, version_id)
        if version is None:
            message = "Generated media version is missing"
            raise ValueError(message)
        manifest: list[dict[str, JsonValue]] = []
        for raw in version.manifest:
            file = FileItem.model_validate(raw)
            probe = probe_file(file)
            durations[file.id] = probe.duration_ms
            manifest.append(
                file.model_copy(
                    update={
                        "metadata": {**file.metadata, "media_probe": probe.model_dump(mode="json")}
                    }
                ).model_dump(mode="json")
            )
        version.manifest = manifest
        session.commit()
    return durations
