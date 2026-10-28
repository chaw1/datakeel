# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Process point-cloud files independently so one unreadable file cannot fail a batch."""

from collections.abc import Callable
from typing import Any

from pydantic import JsonValue

from datakeel.core.errors import ValidationError
from datakeel.core.models import FileItem
from datakeel.operators import failures
from datakeel.operators.base import OperatorResult

FILE_ERRORS = (ValidationError, OSError, ValueError)
ERROR_KEY = "pointcloud_error"
POINTCLOUD_FAILURE = failures.FailureKind(ERROR_KEY, "pointcloud_unreadable", FILE_ERRORS)


def file_error(file: FileItem) -> dict[str, JsonValue] | None:
    """Return the recorded failure of an earlier point-cloud operator, if any."""
    return failures.recorded_failure(file, POINTCLOUD_FAILURE)


def failed_file(file: FileItem, operator: str, error: Exception) -> FileItem:
    """Pass the source through unchanged except for the operator and reason of failure."""
    return failures.failed_file(file, POINTCLOUD_FAILURE, operator, error)


def summarize_batch(
    files: list[FileItem], output: list[FileItem], issues: list[dict[str, Any]] | None = None
) -> OperatorResult:
    """Summarize retained files and mark the result partial when any file failed."""
    return failures.summarize_batch(files, output, POINTCLOUD_FAILURE, issues)


def each_file(
    files: list[FileItem], operator: str, handle: Callable[[FileItem], FileItem]
) -> OperatorResult:
    """Apply a per-file step, recording read or validation failures instead of raising."""
    return failures.each_file(files, operator, handle, POINTCLOUD_FAILURE)
