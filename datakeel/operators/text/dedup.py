# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Deduplicate exact normalized text and approximate token overlap."""

import hashlib
import re
from pathlib import Path
from typing import Any

from datakeel.core.models import FileItem
from datakeel.operators.base import Operator, OperatorResult, TextDedupParams, summarize


def execute(files: list[FileItem], _output_dir: Path, params: TextDedupParams) -> OperatorResult:
    """Deduplicate exact normalized text and approximate token overlap."""
    seen: set[str] = set()
    token_sets: list[set[str]] = []
    output: list[FileItem] = []
    issues: list[dict[str, Any]] = []
    for file in files:
        text = " ".join(Path(file.path).read_text(encoding="utf-8").casefold().split())
        digest = hashlib.sha256(text.encode()).hexdigest()
        tokens = set(re.findall(r"\w+", text))
        duplicate = digest in seen
        if params.approximate and tokens and not duplicate:
            duplicate = any(
                len(tokens & prior) / len(tokens | prior) >= params.threshold
                for prior in token_sets
            )
        if duplicate:
            issues.append({"file_id": file.id, "code": "text_duplicate", "severity": "info"})
        else:
            output.append(file)
            seen.add(digest)
            token_sets.append(tokens)
    return summarize(files, output, issues)


OPERATOR = Operator("text.dedup", "text", "deduplication", TextDedupParams, execute)
