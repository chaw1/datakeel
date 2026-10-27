# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Bounded local ffmpeg execution and deterministic immutable media artifacts."""

import hashlib
import json
import shutil
import subprocess
from fractions import Fraction
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import numpy as np

from datakeel.core.errors import ExecutionError, ValidationError
from datakeel.core.media_alignment import MediaAlignment
from datakeel.core.media_models import MediaProbe, MediaStep
from datakeel.core.models import FileItem

if TYPE_CHECKING:
    from numpy.typing import NDArray
    from pydantic import JsonValue

    from datakeel.operators.base import Params


def _run(arguments: list[str]) -> subprocess.CompletedProcess[bytes]:
    if not arguments or arguments[0] not in {"ffmpeg", "ffprobe"}:
        msg = "Media commands must use ffmpeg or ffprobe"
        raise ValidationError(msg)
    executable = shutil.which(arguments[0])
    if executable is None:
        msg = "Install ffmpeg and ffprobe: brew install ffmpeg, or apt-get install ffmpeg"
        raise ExecutionError(msg)
    prefix = [executable, "-protocol_whitelist", "file,pipe"]
    if arguments[0] == "ffmpeg":
        prefix.extend(["-nostdin", "-threads", "1", "-filter_threads", "1"])
    try:
        result = subprocess.run(  # noqa: S603  # Executable resolved from an explicit allowlist.
            [*prefix, *arguments[1:]], capture_output=True, timeout=300, check=False
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        msg = f"Local media command failed: {type(error).__name__}"
        raise ExecutionError(msg) from error
    if result.returncode:
        diagnostic = result.stderr.decode(errors="replace")[-2000:]
        msg = f"{arguments[0]} could not process recording: {diagnostic}"
        raise ExecutionError(msg)
    return result


def input_path(file: FileItem) -> str:
    """Name a local recording so ffmpeg never reads it as an option or a protocol.

    A relative name such as ``-take.wav`` is a positional option to ffprobe, and
    ``cam:1.mp4`` or ``pipe:0`` select protocols; an absolute path is neither.
    """
    return str(Path(file.path).absolute())


def run_tool(arguments: list[str]) -> bytes:
    """Run one local media command and return its standard output."""
    return _run(arguments).stdout


def run_tool_stderr(arguments: list[str]) -> bytes:
    """Run one local media measurement and return its diagnostic output."""
    return _run(arguments).stderr


def probe_file(file: FileItem) -> MediaProbe:
    """Read local media headers without permitting network protocols."""
    document = json.loads(
        run_tool(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_streams",
                "-show_format",
                "-of",
                "json",
                input_path(file),
            ]
        )
    )
    streams = document.get("streams", [])
    videos = [stream for stream in streams if stream.get("codec_type") == "video"]
    audios = [stream for stream in streams if stream.get("codec_type") == "audio"]
    stream: dict[str, Any] = videos[0] if videos else audios[0] if audios else {}
    audio: dict[str, Any] = audios[0] if audios else {}
    duration = document.get("format", {}).get("duration", stream.get("duration", "0"))
    rate = stream.get("avg_frame_rate", "0/1")
    rotation = int(stream.get("tags", {}).get("rotate", 0))
    for side in stream.get("side_data_list", []):
        rotation = int(side.get("rotation", rotation))
    return MediaProbe(
        duration_ms=round(float(duration) * 1000),
        format=str(document.get("format", {}).get("format_name", "")),
        codec=str(stream.get("codec_name", "")),
        width=int(stream.get("width", 0)),
        height=int(stream.get("height", 0)),
        frame_rate=float(Fraction(rate)) if rate not in {"0/0", "N/A"} else 0,
        rotation=rotation,
        audio_tracks=len(audios),
        sample_rate=int(audio.get("sample_rate", 0)),
        channels=int(audio.get("channels", 0)),
    )


def decode_audio(
    file: FileItem, sample_rate: int = 16000, *, max_duration_seconds: float | None = None
) -> "NDArray[np.float64]":
    """Decode the strongest audio channel without destructive phase cancellation."""
    channels = probe_file(file).channels or 1
    limit = ["-t", str(max_duration_seconds)] if max_duration_seconds is not None else []
    content = run_tool(
        [
            "ffmpeg",
            "-v",
            "error",
            "-i",
            input_path(file),
            "-map",
            "0:a:0",
            "-ar",
            str(sample_rate),
            *limit,
            "-f",
            "f64le",
            "pipe:1",
        ]
    )
    samples = np.frombuffer(content, dtype="<f8").reshape(-1, channels)
    if not samples.size:
        return np.zeros(0, dtype=np.float64)
    strongest = int(np.argmax(np.mean(samples * samples, axis=0)))
    return samples[:, strongest].copy()


def media_artifact(
    file: FileItem,
    output_dir: Path,
    content: bytes,
    extension: str,
    operator: str,
    params: "Params",
    **timing: int | None,
) -> FileItem:
    """Store content-addressed output and freeze its source interval and parameters."""
    start_ms = timing.get("start_ms", 0) or 0
    end_ms = timing.get("end_ms")
    if end_ms is None:
        end_ms = probe_file(file).duration_ms
    if set(timing) - {"start_ms", "end_ms"}:
        msg = "Only start_ms and end_ms are valid artifact timing options"
        raise ValidationError(msg)
    parameters = cast("dict[str, JsonValue]", params.model_dump(mode="json"))
    digest = hashlib.sha256(json.dumps(parameters, sort_keys=True).encode()).hexdigest()
    step = MediaStep(
        operator=operator,
        parameters=parameters,
        parameters_digest=digest,
        source_file_id=file.id,
        start_ms=start_ms,
        end_ms=end_ms,
    )
    identity = hashlib.sha256(
        (file.id + step.model_dump_json() + hashlib.sha256(content).hexdigest()).encode()
    ).hexdigest()
    path = output_dir / f"{identity}.{extension}"
    output_dir.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    metadata = {**_artifact_metadata(file, step), "format": extension, "empty": not content}
    result = FileItem(
        id=identity,
        path=str(path.resolve()),
        filename=f"{Path(file.filename).stem}.{extension}",
        sha256=hashlib.sha256(content).hexdigest(),
        size=len(content),
        modality=file.modality,
        metadata=metadata,
    )
    return result.model_copy(
        update={
            "metadata": {
                **result.metadata,
                "media_probe": probe_file(result).model_dump(mode="json"),
            }
        }
    )


def _artifact_metadata(file: FileItem, step: MediaStep) -> dict[str, Any]:
    start_ms, end_ms = step.start_ms, step.end_ms
    metadata = {
        **file.metadata,
        "source_file_id": file.id,
        "source_asset_id": file.metadata.get("source_asset_id", file.id),
        "start_ms": start_ms,
        "end_ms": end_ms,
        "operator": step.operator,
        "operator_version": step.version,
        "parameters_digest": step.parameters_digest,
        "media_history": [*file.metadata.get("media_history", []), step.model_dump(mode="json")],
        "corrupt": False,
        "empty": False,
    }
    for key in ("media_probe", "media_issues", "video_metrics", "audio_metrics"):
        metadata.pop(key, None)
    metadata["source_start_ms"] = int(file.metadata.get("source_start_ms", 0)) + start_ms
    metadata["source_end_ms"] = (
        int(file.metadata.get("source_start_ms", 0)) + end_ms if end_ms is not None else None
    )
    if file.metadata.get("media_alignment"):
        alignment = MediaAlignment.model_validate(file.metadata["media_alignment"])
        if alignment.aligned and alignment.offset_ms is not None:
            alignment = alignment.model_copy(
                update={
                    "offset_ms": alignment.offset_ms - start_ms,
                    "reason": "matched" if start_ms else alignment.reason,
                }
            )
        metadata["media_alignment"] = alignment.model_dump(mode="json")
    return metadata
