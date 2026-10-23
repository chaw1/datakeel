# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Content hash deduplication, independent of untrusted stored hashes."""

import hashlib
from pathlib import Path
from typing import Any

from datakeel.core.models import FileItem
from datakeel.operators.base import EmptyParams, Operator, OperatorResult, summarize


def execute(files: list[FileItem], _output_dir: Path, _params: EmptyParams) -> OperatorResult:
    """Content hash deduplication, independent of untrusted stored hashes."""
    seen: set[str] = set()
    output: list[FileItem] = []
    issues: list[dict[str, Any]] = []
    for file in files:
        with Path(file.path).open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        if digest in seen:
            issues.append({"file_id": file.id, "code": "duplicate", "severity": "info"})
        else:
            seen.add(digest)
            output.append(file.model_copy(update={"sha256": digest}, deep=True))
    return summarize(files, output, issues)


OPERATOR = Operator("file.dedup", "any", "deduplication", EmptyParams, execute, "io")
