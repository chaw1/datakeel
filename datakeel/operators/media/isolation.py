# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Confine a recording's decode or processing failure to that recording.

A failed recording keeps its bytes and gains a ``media_failure`` record naming the
operator and the reason. Later media operators pass it through untouched, so the
other recordings in the same task are still processed and published.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from datakeel.core.errors import ExecutionError, ValidationError
from datakeel.core.media_metadata import FAILURE_KEY

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from datakeel.core.models import FileItem
    from datakeel.operators.base import OperatorResult, Params

__all__ = ["FAILURE_KEY", "MEDIA_ERRORS", "has_failed", "mark_failed", "run_isolated"]

MEDIA_ERRORS = (ExecutionError, ValidationError)
_PAIRWISE = frozenset({"media.align", "audio.dedup", "video.dedup"})
_REASON_LIMIT = 1000


def has_failed(file: FileItem) -> bool:
    """Report whether an earlier media operator could not process this recording."""
    return bool(file.metadata.get(FAILURE_KEY))


def mark_failed(file: FileItem, operator: str, error: Exception) -> FileItem:
    """Record which operator failed on this recording and why, keeping its bytes."""
    reason = f"{type(error).__name__}: {error}"[:_REASON_LIMIT]
    failure = {"operator": operator, "reason": reason}
    return file.model_copy(update={"metadata": {**file.metadata, FAILURE_KEY: failure}}, deep=True)


def run_isolated(
    operator: str,
    execute: Callable[[list[FileItem], Path, Any], OperatorResult],
    files: list[FileItem],
    output_dir: Path,
    params: Params,
) -> OperatorResult:
    """Execute healthy recordings and isolate each one's failure to that recording.

    Per-recording operators run once per file. Pairwise operators (alignment and
    deduplication) need every recording at once and isolate decode failures
    themselves through :func:`mark_failed`.
    """
    from datakeel.operators.base import OperatorResult  # noqa: PLC0415  # Avoid registry cycle.

    healthy = [file for file in files if not has_failed(file)]
    passed = [file for file in files if has_failed(file)]
    if operator in _PAIRWISE:
        parts = [execute(healthy, output_dir, params)] if healthy or not files else []
    else:
        parts = [_single(operator, execute, file, output_dir, params) for file in healthy]
    produced = [output for part in parts for output in part.files]
    failed = sorted(output.id for output in produced if has_failed(output))
    quality = _merge([part.quality for part in parts])
    quality.update(
        input_count=len(files),
        output_count=len(produced) + len(passed),
        removed_count=len(files) - len(produced) - len(passed),
        failed_files=failed,
    )
    return OperatorResult(files=[*produced, *passed], quality=quality)


def _single(
    operator: str,
    execute: Callable[[list[FileItem], Path, Any], OperatorResult],
    file: FileItem,
    output_dir: Path,
    params: Params,
) -> OperatorResult:
    from datakeel.operators.base import OperatorResult  # noqa: PLC0415  # Avoid registry cycle.

    try:
        return execute([file], output_dir, params)
    except MEDIA_ERRORS as error:
        return OperatorResult(files=[mark_failed(file, operator, error)])


def _merge(qualities: list[dict[str, Any]]) -> dict[str, Any]:
    """Sum counters and concatenate lists reported by per-recording executions."""
    merged: dict[str, Any] = {}
    for quality in qualities:
        for key, value in quality.items():
            current = merged.get(key)
            if isinstance(value, list) and isinstance(current, list):
                merged[key] = [*current, *value]
            elif isinstance(value, int | float) and isinstance(current, int | float):
                merged[key] = current + value
            else:
                merged[key] = value
    return merged
