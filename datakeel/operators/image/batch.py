# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Isolate undecodable or out-of-bounds images so the rest of a batch is still processed."""

from collections.abc import Callable
from typing import Any

from PIL import Image

from datakeel.core.models import FileItem
from datakeel.operators import failures
from datakeel.operators.base import OperatorResult

# Pillow reports unknown or damaged data as OSError (including
# UnidentifiedImageError) and, from some format plugins, SyntaxError or
# EOFError. Byte, pixel and parameter limits are ValueErrors, and a
# decompression bomb has its own class; each is a fault of one file.
FILE_ERRORS = (OSError, ValueError, SyntaxError, EOFError, Image.DecompressionBombError)
IMAGE_FAILURE = failures.FailureKind("image_error", "image_unreadable", FILE_ERRORS)


def guarded(
    operator: str, handle: Callable[[FileItem], FileItem]
) -> Callable[[FileItem], FileItem]:
    """Skip images an earlier step could not read and record this step's file faults."""
    return failures.guarded(IMAGE_FAILURE, operator, handle)


def summarize_batch(
    files: list[FileItem], output: list[FileItem], issues: list[dict[str, Any]] | None = None
) -> OperatorResult:
    """Summarize retained images and mark the result partial when any image failed."""
    return failures.summarize_batch(files, output, IMAGE_FAILURE, issues)
