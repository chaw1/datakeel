# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Redact email addresses and common international or local phone patterns."""

import re
from pathlib import Path

from datakeel.core.models import FileItem
from datakeel.operators.base import Operator, OperatorResult, PiiParams, artifact, summarize

EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
PHONE = re.compile(r"(?<![\w/-])(?!(?:\d{4}-\d{2}-\d{2})(?!\d))(?:\+?\d[\d ()-]{7,}\d)(?!\w)")


def execute(files: list[FileItem], output_dir: Path, params: PiiParams) -> OperatorResult:
    """Redact email addresses and common international or local phone patterns."""
    output: list[FileItem] = []
    count = 0
    for file in files:
        text = Path(file.path).read_text(encoding="utf-8")
        redactions = 0
        for enabled, pattern in [(params.emails, EMAIL), (params.phones, PHONE)]:
            if enabled:
                text, matches = pattern.subn(lambda _: params.replacement, text)
                redactions += matches
        count += redactions
        output.append(
            artifact(file, output_dir, text.encode("utf-8"), "txt", pii_redactions=redactions)
        )
    result = summarize(files, output)
    result.quality["redactions"] = count
    return result


OPERATOR = Operator("text.pii_redact", "text", "privacy", PiiParams, execute)
