# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Process point-cloud files independently so one unreadable file cannot fail a batch."""

from collections.abc import Callable
from typing import Any, cast

from pydantic import JsonValue

from datakeel.core.errors import ValidationError
from datakeel.core.models import FileItem
from datakeel.operators.base import OperatorResult, annotate, summarize

FILE_ERRORS = (ValidationError, OSError, ValueError)
ERROR_KEY = "pointcloud_error"


def file_error(file: FileItem) -> dict[str, JsonValue] | None:
    """Return the recorded failure of an earlier point-cloud operator, if any."""
    value = file.metadata.get(ERROR_KEY)
    return cast("dict[str, JsonValue]", value) if isinstance(value, dict) else None


def failed_file(file: FileItem, operator: str, error: Exception) -> FileItem:
    """Pass the source through unchanged except for the operator and reason of failure."""
    reason = f"{type(error).__name__}: {error}"
    detail: dict[str, JsonValue] = {"operator": operator, "reason": reason}
    return annotate(file, **{ERROR_KEY: detail})


def summarize_batch(
    files: list[FileItem], output: list[FileItem], issues: list[dict[str, Any]] | None = None
) -> OperatorResult:
    """Summarize retained files and mark the result partial when any file failed.

    A failed file stays in the output with its reason, like a failed image in
    an extraction batch, so reports can show it and later steps skip it.
    """
    failures = [(file, error) for file in output if (error := file_error(file)) is not None]
    all_issues = list(issues or [])
    all_issues.extend(
        {
            "file_id": file.id,
            "code": "pointcloud_unreadable",
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


def each_file(
    files: list[FileItem], operator: str, handle: Callable[[FileItem], FileItem]
) -> OperatorResult:
    """Apply a per-file step, recording read or validation failures instead of raising."""
    output: list[FileItem] = []
    for file in files:
        if file_error(file) is not None:
            output.append(file)
            continue
        try:
            output.append(handle(file))
        except FILE_ERRORS as error:
            output.append(failed_file(file, operator, error))
    return summarize_batch(files, output)
