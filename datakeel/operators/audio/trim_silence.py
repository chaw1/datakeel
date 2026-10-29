# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Remove edge silence and preserve the source time interval of retained audio."""

from pathlib import Path

from datakeel.core.models import FileItem
from datakeel.operators.audio.common import (
    activity_metrics,
    annotate_audio,
    measure_activity,
)
from datakeel.operators.audio.params import TrimParams
from datakeel.operators.audio.streaming import stream_artifact
from datakeel.operators.base import Operator, OperatorResult, summarize
from datakeel.operators.media.tools import (
    input_path,
)


def execute(files: list[FileItem], output_dir: Path, params: TrimParams) -> OperatorResult:
    """Trim only leading/trailing silence and drop files without detected activity."""
    output: list[FileItem] = []
    for file in files:
        measured = measure_activity(file, params)
        if not measured.active:
            continue
        start_ms = max(0, measured.active[0].start_ms - params.padding_ms)
        end_ms = min(measured.duration_ms, measured.active[-1].end_ms + params.padding_ms)
        trimmed = stream_artifact(
            file,
            output_dir,
            [
                "ffmpeg",
                "-v",
                "error",
                "-i",
                input_path(file),
                "-af",
                f"atrim=start={start_ms / 1000}:end={end_ms / 1000},asetpts=PTS-STARTPTS",
                "-map",
                "0:a:0",
                "-map_metadata",
                "-1",
                "-c:a",
                "pcm_s16le",
                "-fflags",
                "+bitexact",
                "-flags:a",
                "+bitexact",
                "-f",
                "wav",
                "pipe:1",
            ],
            "audio.trim_silence",
            params,
            start_ms=start_ms,
            end_ms=end_ms,
        )
        remaining = measure_activity(trimmed, params)
        output.append(annotate_audio(trimmed, activity_metrics(remaining), remaining.silent))
    return summarize(files, output)


OPERATOR = Operator("audio.trim_silence", "audio", "transformation", TrimParams, execute)
