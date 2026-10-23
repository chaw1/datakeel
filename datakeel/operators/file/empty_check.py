# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Mark or remove empty and whitespace-only text artifacts."""

from pathlib import Path
from typing import Any

from datakeel.core.models import FileItem
from datakeel.operators.base import FilterParams, Operator, OperatorResult, annotate, summarize


def execute(files: list[FileItem], _output_dir: Path, params: FilterParams) -> OperatorResult:
    """Mark or remove empty and whitespace-only text artifacts."""
    output: list[FileItem] = []
    issues: list[dict[str, Any]] = []
    for file in files:
        path = Path(file.path)
        empty = path.stat().st_size == 0
        if file.modality == "text" and not empty:
            with path.open("rb") as stream:
                empty = all(not chunk.strip() for chunk in iter(lambda: stream.read(65536), b""))
        marked = annotate(file, empty=empty)
        if empty:
            issues.append({"file_id": file.id, "code": "empty", "severity": "critical"})
        if not (empty and params.remove):
            output.append(marked)
    return summarize(files, output, issues)


OPERATOR = Operator("file.empty_check", "any", "validation", FilterParams, execute, "io")
