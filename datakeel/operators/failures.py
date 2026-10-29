# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Record per-file failures so one unreadable file cannot fail a whole batch."""

from collections.abc import Callable
from pathlib import Path
from typing import Any, NamedTuple, cast

from pydantic import JsonValue

from datakeel.core.models import FileItem
from datakeel.operators.base import OperatorResult, annotate, summarize


class FailureKind(NamedTuple):
    """Name where a modality records a failed file and which errors count as file faults."""

    key: str
    code: str
    errors: tuple[type[Exception], ...]


def recorded_failure(file: FileItem, kind: FailureKind) -> dict[str, JsonValue] | None:
    """Return the failure an earlier operator recorded for this file, if any."""
    value = file.metadata.get(kind.key)
    return cast("dict[str, JsonValue]", value) if isinstance(value, dict) else None


def failed_file(file: FileItem, kind: FailureKind, operator: str, error: Exception) -> FileItem:
    """Pass the source through unchanged except for the operator and reason of failure.

    Decoders often quote the storage path; reports name the file instead.
    """
    reason = f"{type(error).__name__}: {error}".replace(str(Path(file.path)), file.filename)
    detail: dict[str, JsonValue] = {"operator": operator, "reason": reason}
    return annotate(file, **{kind.key: detail})


def summarize_batch(
    files: list[FileItem],
    output: list[FileItem],
    kind: FailureKind,
    issues: list[dict[str, Any]] | None = None,
) -> OperatorResult:
    """Summarize retained files and mark the result partial when any file failed.

    A failed file stays in the output with its reason, like a failed image in
    an extraction batch, so reports can show it and later steps skip it.
    """
    failures = [
        (file, error) for file in output if (error := recorded_failure(file, kind)) is not None
    ]
    all_issues = list(issues or [])
    all_issues.extend(
        {
            "file_id": file.id,
            "code": kind.code,
            "severity": "error",
            "reason": f"{error.get('operator')}: {error.get('reason')}",
        }
        for file, error in failures
    )
    result = summarize(files, output, all_issues)
    result.quality["failed_count"] = len(failures)
    result.quality["partial"] = bool(failures)
    result.quality["failed_files"] = [
        {"file_id": file.id, "filename": file.filename, **error} for file, error in failures
    ]
    return result


def guarded(
    kind: FailureKind, operator: str, handle: Callable[[FileItem], FileItem]
) -> Callable[[FileItem], FileItem]:
    """Wrap a per-file step to skip earlier failures and record its own file faults."""

    def run(file: FileItem) -> FileItem:
        if recorded_failure(file, kind) is not None:
            return file
        try:
            return handle(file)
        except kind.errors as error:
            return failed_file(file, kind, operator, error)

    return run


def each_file(
    files: list[FileItem],
    operator: str,
    handle: Callable[[FileItem], FileItem],
    kind: FailureKind,
) -> OperatorResult:
    """Apply a per-file step in order, recording file faults instead of raising."""
    step = guarded(kind, operator, handle)
    return summarize_batch(files, [step(file) for file in files], kind)
