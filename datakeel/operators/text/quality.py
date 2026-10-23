# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Measure text length, word count and readable character ratio."""

import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

from datakeel.core.models import FileItem
from datakeel.operators.base import Operator, OperatorResult, TextQualityParams, annotate, summarize

if TYPE_CHECKING:
    from pydantic import JsonValue


def execute(files: list[FileItem], _output_dir: Path, params: TextQualityParams) -> OperatorResult:
    """Measure text length, word count and readable character ratio."""
    output: list[FileItem] = []
    issues: list[dict[str, Any]] = []
    measurements: dict[str, Any] = {}
    for file in files:
        text = Path(file.path).read_text(encoding="utf-8")
        ratio = sum(char.isprintable() or char.isspace() for char in text) / max(1, len(text))
        problems: list[str] = []
        if len(text.strip()) < params.min_characters:
            problems.append("short_text")
        if ratio < params.min_printable_ratio:
            problems.append("non_printable")
        quality: dict[str, JsonValue] = {
            "characters": len(text),
            "words": len(re.findall(r"\w+", text)),
            "printable_ratio": round(ratio, 4),
            "issues": list(problems),
        }
        measurements[file.id] = quality
        output.append(annotate(file, text_quality=quality))
        issues.extend(
            {"file_id": file.id, "code": code, "severity": "warning"} for code in problems
        )
    result = summarize(files, output, issues)
    result.quality["measurements"] = measurements
    return result


OPERATOR = Operator("text.quality", "text", "quality", TextQualityParams, execute)
