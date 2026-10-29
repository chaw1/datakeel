# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Bounded local ffmpeg execution and deterministic immutable media artifacts."""

import hashlib
import json
import math
import shutil
from fractions import Fraction
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import numpy as np

from datakeel.core.errors import ExecutionError, ValidationError
from datakeel.core.media_alignment import MediaAlignment
from datakeel.core.media_models import MediaProbe, MediaStep
from datakeel.core.models import FileItem
from datakeel.operators.media.command import (
    input_path,
    media_timeout,
    run_tool,
    run_tool_stderr,
    stream_tool,
)

__all__ = [
    "TRUNCATION_TOLERANCE_MS",
    "decode_audio",
    "input_path",
    "media_artifact",
    "media_timeout",
    "probe_file",
    "run_tool",
    "run_tool_stderr",
    "stream_tool",
]

if TYPE_CHECKING:
    from numpy.typing import NDArray
    from pydantic import JsonValue

    from datakeel.operators.base import Params


TRUNCATION_TOLERANCE_MS = 500
_RIFF_HEADER = 12
_CHUNK_HEADER = 8
_FMT_BYTE_RATE = slice(8, 12)
_UNKNOWN_RIFF_SIZE = 0xFFFFFFFF


def probe_file(file: FileItem) -> MediaProbe:
    """Read local media headers and the readable stream extent, cached per file version.

    When the header promises noticeably more than the stored packets contain, the
    probe reports the readable duration and keeps the header's claim separately.
    """
    path = Path(input_path(file))
    try:
        status = path.stat()
    except OSError as error:
        msg = f"Recording is not readable: {type(error).__name__}"
        raise ExecutionError(msg) from error
    return _probe(str(path), status.st_size, status.st_mtime_ns)


@lru_cache(maxsize=256)
def _probe(path: str, _size: int, _modified_ns: int) -> MediaProbe:
    document = json.loads(
        run_tool(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", path])
    )
    streams = document.get("streams", [])
    videos = [stream for stream in streams if stream.get("codec_type") == "video"]
    audios = [stream for stream in streams if stream.get("codec_type") == "audio"]
    stream: dict[str, Any] = videos[0] if videos else audios[0] if audios else {}
    audio: dict[str, Any] = audios[0] if audios else {}
    form = document.get("format", {})
    header = _seconds(form.get("duration", stream.get("duration")))
    readable = _readable_ms(path, _seconds(form.get("start_time")) or 0.0, header)
    declared = max(round((header or 0) * 1000), _riff_declared_ms(path) or 0) or readable
    truncated = declared - readable > TRUNCATION_TOLERANCE_MS
    rate = stream.get("avg_frame_rate", "0/1")
    rotation = int(stream.get("tags", {}).get("rotate", 0))
    for side in stream.get("side_data_list", []):
        rotation = int(side.get("rotation", rotation))
    return MediaProbe(
        duration_ms=readable if truncated else declared,
        declared_duration_ms=declared if truncated else None,
        format=str(form.get("format_name", "")),
        codec=str(stream.get("codec_name", "")),
        width=int(stream.get("width", 0)),
        height=int(stream.get("height", 0)),
        frame_rate=float(Fraction(rate)) if rate not in {"0/0", "N/A"} else 0,
        rotation=rotation,
        audio_tracks=len(audios),
        sample_rate=int(audio.get("sample_rate", 0)),
        channels=int(audio.get("channels", 0)),
    )


def _seconds(value: object) -> float | None:
    try:
        number = float(str(value))
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def _readable_ms(path: str, start: float, header: float | None) -> int:
    """Measure where the stored packets end, without decoding them."""
    listing = run_tool(
        [
            "ffprobe",
            "-v",
            "quiet",
            "-show_entries",
            "packet=pts_time,dts_time,duration_time",
            "-of",
            "csv=p=0",
            path,
        ],
        timeout=media_timeout(round((header or 0) * 1000)),
    )
    end = 0.0
    for line in listing.decode(errors="replace").splitlines():
        fields = [*line.split(","), "", "", ""][:3]
        stamp = _seconds(fields[0]) if fields[0] not in {"", "N/A"} else _seconds(fields[1])
        if stamp is not None:
            end = max(end, stamp + (_seconds(fields[2]) or 0.0))
    return max(0, round((end - start) * 1000))


def _riff_declared_ms(path: str) -> int | None:
    """Read the duration a WAV header promises, which ffprobe clamps to the file size."""
    with Path(path).open("rb") as handle:
        header = handle.read(_RIFF_HEADER)
        if header[:4] != b"RIFF" or header[8:12] != b"WAVE":
            return None
        byte_rate = 0
        while chunk := handle.read(_CHUNK_HEADER):
            if len(chunk) < _CHUNK_HEADER:
                return None
            identifier, size = chunk[:4], int.from_bytes(chunk[4:], "little")
            if identifier == b"data":
                if not byte_rate or size in {0, _UNKNOWN_RIFF_SIZE}:
                    return None
                return round(size * 1000 / byte_rate)
            payload = handle.read(size + size % 2)
            if identifier == b"fmt ":
                byte_rate = int.from_bytes(payload[_FMT_BYTE_RATE], "little")
    return None


def decode_audio(
    file: FileItem, sample_rate: int = 16000, *, max_duration_seconds: float | None = None
) -> "NDArray[np.float64]":
    """Decode the strongest audio channel without destructive phase cancellation."""
    probe = probe_file(file)
    channels = probe.channels or 1
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
        ],
        timeout=media_timeout(probe.duration_ms),
    )
    samples = np.frombuffer(content, dtype="<f8").reshape(-1, channels)
    if not samples.size:
        return np.zeros(0, dtype=np.float64)
    strongest = int(np.argmax(np.mean(samples * samples, axis=0)))
    return samples[:, strongest].copy()


def media_artifact(
    file: FileItem,
    output_dir: Path,
    content: bytes | Path,
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
        (file.id + step.model_dump_json() + _content_digest(content)).encode()
    ).hexdigest()
    path = output_dir / f"{identity}.{extension}"
    output_dir.mkdir(parents=True, exist_ok=True)
    if isinstance(content, Path):
        shutil.copyfile(content, path)
    else:
        path.write_bytes(content)
    size = path.stat().st_size
    metadata = {**_artifact_metadata(file, step), "format": extension, "empty": size == 0}
    result = FileItem(
        id=identity,
        path=str(path.resolve()),
        filename=f"{Path(file.filename).stem}.{extension}",
        sha256=_content_digest(content),
        size=size,
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


def _content_digest(content: bytes | Path) -> str:
    if isinstance(content, Path):
        with content.open("rb") as handle:
            return hashlib.file_digest(handle, "sha256").hexdigest()
    return hashlib.sha256(content).hexdigest()


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
