# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Run allowlisted local ffmpeg/ffprobe commands within a media-scaled time budget."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path
from typing import TYPE_CHECKING

from datakeel.core.errors import ExecutionError, ValidationError
from datakeel.core.settings import get_settings

if TYPE_CHECKING:
    from collections.abc import Iterator
    from typing import IO

    from datakeel.core.models import FileItem

_PROGRAMS = frozenset({"ffmpeg", "ffprobe"})
_REFERENCE_PIXELS = 1920 * 1080
_MAX_AUTOMATIC_THREADS = 8
_DIAGNOSTIC_BYTES = 2000


def input_path(file: FileItem) -> str:
    """Name a local recording so ffmpeg never reads it as an option or a protocol.

    A relative name such as ``-take.wav`` is a positional option to ffprobe, and
    ``cam:1.mp4`` or ``pipe:0`` select protocols; an absolute path is neither.
    """
    return str(Path(file.path).absolute())


def decoder_threads() -> int:
    """Return the configured decoder thread count; ``0`` selects a bounded automatic value."""
    configured = get_settings().media_threads
    return configured or max(1, min(_MAX_AUTOMATIC_THREADS, os.cpu_count() or 1))


def media_timeout(duration_ms: int, width: int = 0, height: int = 0) -> float:
    """Scale a command's time budget with media length and resolution, up to a hard cap.

    The budget is ``base + ratio * seconds * max(1, pixels / 1080p)``; a 1080p
    recording at the default ratio may take twice its own duration on top of the base.
    """
    settings = get_settings()
    scale = max(1.0, (width * height) / _REFERENCE_PIXELS)
    budget = settings.media_timeout_base_seconds + (
        settings.media_timeout_ratio * (duration_ms / 1000) * scale
    )
    return min(settings.media_timeout_max_seconds, budget)


def _command(arguments: list[str]) -> list[str]:
    if not arguments or arguments[0] not in _PROGRAMS:
        msg = "Media commands must use ffmpeg or ffprobe"
        raise ValidationError(msg)
    executable = shutil.which(arguments[0])
    if executable is None:
        msg = "Install ffmpeg and ffprobe: brew install ffmpeg, or apt-get install ffmpeg"
        raise ExecutionError(msg)
    prefix = [executable, "-protocol_whitelist", "file,pipe"]
    if arguments[0] == "ffmpeg":
        threads = str(decoder_threads())
        prefix.extend(["-nostdin", "-threads", threads, "-filter_threads", threads])
    return [*prefix, *arguments[1:]]


def _failure(program: str, diagnostic: bytes) -> ExecutionError:
    text = diagnostic.decode(errors="replace")[-_DIAGNOSTIC_BYTES:]
    return ExecutionError(f"{program} could not process recording: {text}")


def _run(arguments: list[str], timeout: float | None) -> subprocess.CompletedProcess[bytes]:
    command = _command(arguments)
    limit = timeout if timeout is not None else get_settings().media_timeout_base_seconds
    try:
        result = subprocess.run(  # noqa: S603  # Executable resolved from an explicit allowlist.
            command, capture_output=True, timeout=limit, check=False
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        msg = f"Local media command failed: {type(error).__name__}"
        raise ExecutionError(msg) from error
    if result.returncode:
        raise _failure(arguments[0], result.stderr)
    return result


def run_tool(arguments: list[str], *, timeout: float | None = None) -> bytes:
    """Run one local media command and return its standard output."""
    return _run(arguments, timeout).stdout


def run_tool_stderr(arguments: list[str], *, timeout: float | None = None) -> bytes:
    """Run one local media measurement and return its diagnostic output."""
    return _run(arguments, timeout).stderr


def stream_tool(
    arguments: list[str], chunk: int, *, timeout: float, allow_partial: bool = False
) -> Iterator[bytes]:
    """Yield fixed-size output records while the command runs, within a hard time budget.

    Long recordings are analysed without holding every decoded frame in memory. A
    watchdog kills the process when the budget expires, and a nonzero exit or a
    trailing partial record is an explicit failure.
    """
    command = _command(arguments)
    expired = threading.Event()
    with tempfile.TemporaryFile() as diagnostics:
        try:
            process = subprocess.Popen(  # noqa: S603  # Allowlisted executable, no shell.
                command, stdout=subprocess.PIPE, stderr=diagnostics
            )
        except OSError as error:
            msg = f"Local media command failed: {type(error).__name__}"
            raise ExecutionError(msg) from error

        def expire() -> None:
            expired.set()
            process.kill()

        watchdog = threading.Timer(timeout, expire)
        watchdog.start()
        partial = False
        try:
            stdout = process.stdout
            if stdout is None:  # pragma: no cover - guaranteed by stdout=PIPE.
                msg = "Local media command has no output stream"
                raise ExecutionError(msg)
            while record := stdout.read(chunk):
                if len(record) != chunk:
                    if allow_partial:
                        yield record
                    else:
                        partial = True
                    break
                yield record
            code = process.wait()
        finally:
            watchdog.cancel()
            if process.poll() is None:
                process.kill()
                process.wait()
        _stream_outcome(arguments[0], diagnostics, code, expired=expired.is_set(), partial=partial)


def _stream_outcome(
    program: str, diagnostics: IO[bytes], code: int, *, expired: bool, partial: bool
) -> None:
    if expired:
        msg = "Local media command failed: TimeoutExpired"
        raise ExecutionError(msg)
    if code:
        diagnostics.seek(0)
        raise _failure(program, diagnostics.read())
    if partial:
        msg = f"{program} produced a truncated output record"
        raise ExecutionError(msg)
