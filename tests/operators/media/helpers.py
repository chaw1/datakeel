# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Create isolated media fixtures exclusively from local lavfi signals."""

from pathlib import Path

from datakeel.core.models import FileItem
from datakeel.operators.media.tools import run_tool


def audio_file(directory: Path, name: str, source: str) -> FileItem:
    """Generate one mono lossless recording from a lavfi audio source."""
    path = directory / f"{name}.wav"
    run_tool(["ffmpeg", "-y", "-f", "lavfi", "-i", source, "-c:a", "pcm_s16le", str(path)])
    return FileItem(id=name, path=str(path), filename=path.name, modality="audio")


def shifted_file(file: FileItem, offset_ms: int) -> FileItem:
    """Delay or crop a generated source without changing its shared signal."""
    path = Path(file.path).with_name(f"shift-{offset_ms}-{file.filename}")
    audio_filter = (
        f"adelay={offset_ms}:all=1"
        if offset_ms >= 0
        else f"atrim=start={-offset_ms / 1000},asetpts=PTS-STARTPTS"
    )
    run_tool(["ffmpeg", "-y", "-i", file.path, "-af", audio_filter, "-c:a", "pcm_s16le", str(path)])
    return FileItem(
        id=path.stem,
        path=str(path),
        filename=path.name,
        modality="audio",
    )
