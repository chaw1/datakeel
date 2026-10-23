# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Validate image decoding and readable file content without changing encodings."""

from pathlib import Path
from typing import Any

from PIL import Image, UnidentifiedImageError

from datakeel.core.models import FileItem
from datakeel.operators.base import FilterParams, Operator, OperatorResult, annotate, summarize
from datakeel.operators.image.helpers import open_image
from datakeel.operators.image.limits import ImageResourceLimit


def execute(files: list[FileItem], _output_dir: Path, params: FilterParams) -> OperatorResult:
    """Validate image decoding and readable file content without changing encodings."""
    output: list[FileItem] = []
    issues: list[dict[str, Any]] = []
    for file in files:
        issue_code = "corrupt"
        try:
            if file.modality == "image":
                with open_image(file):
                    pass
            else:
                with Path(file.path).open("rb") as stream:
                    stream.read(1)
            corrupt = False
        except ImageResourceLimit:
            corrupt = True
            issue_code = "image_resource_limit"
        except (OSError, ValueError, UnidentifiedImageError, Image.DecompressionBombError):
            corrupt = True
        marked = annotate(file, corrupt=corrupt)
        if corrupt:
            issues.append({"file_id": file.id, "code": issue_code, "severity": "critical"})
        if not (corrupt and params.remove):
            output.append(marked)
    return summarize(files, output, issues)


OPERATOR = Operator("file.corrupt_check", "any", "validation", FilterParams, execute, "io")
