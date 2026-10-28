# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Deduplicate normalized text through disk indexes and bounded LSH candidates."""

from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from datakeel.core.llm_data_models import TrainingConfig
from datakeel.core.models import FileItem
from datakeel.operators.base import Operator, OperatorResult, TextDedupParams, summarize


def execute(files: list[FileItem], _output_dir: Path, params: TextDedupParams) -> OperatorResult:
    """Retain the first representative without pairwise comparisons of all prior files."""
    # The eager registry must finish loading before importing the shared domain engine.
    from datakeel.llm_data.index import DuplicateIndex  # noqa: PLC0415

    output: list[FileItem] = []
    issues: list[dict[str, Any]] = []
    with TemporaryDirectory(prefix="datakeel-text-dedup-") as temporary:
        index = DuplicateIndex(
            Path(temporary) / "index.sqlite", TrainingConfig(near_similarity=params.threshold)
        )
        try:
            for file in files:
                text = Path(file.path).read_text(encoding="utf-8")
                findings = index.check(file.id, text, text, text, approximate=params.approximate)
                if any(item.code.endswith("duplicate") for item in findings):
                    issues.append(
                        {"file_id": file.id, "code": "text_duplicate", "severity": "info"}
                    )
                else:
                    output.append(file)
        finally:
            index.close()
    return summarize(files, output, issues)


OPERATOR = Operator("text.dedup", "text", "deduplication", TextDedupParams, execute)
