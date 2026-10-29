# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Redact validated privacy findings through the shared offline detector."""

from pathlib import Path

from datakeel.core.models import FileItem
from datakeel.core.pii import PiiType, detect_pii, redact_pii
from datakeel.core.pii_patterns import EMAIL, PHONE
from datakeel.operators.base import Operator, OperatorResult, PiiParams, artifact, summarize

__all__ = ["EMAIL", "OPERATOR", "PHONE", "execute"]


def execute(files: list[FileItem], output_dir: Path, params: PiiParams) -> OperatorResult:
    """Redact all privacy classes while retaining existing contact toggles and labels."""
    output: list[FileItem] = []
    count = 0
    kinds: frozenset[PiiType] = frozenset(
        kind
        for kind in ("email", "phone", "china_id", "bank_card", "ip", "secret", "credential_url")
        if (kind != "email" or params.emails) and (kind != "phone" or params.phones)
    )
    replacement = None if params.replacement == "[REDACTED]" else params.replacement
    for file in files:
        text = Path(file.path).read_text(encoding="utf-8")
        redactions = sum(match.type in kinds for match in detect_pii(text))
        text = redact_pii(text, replacement=replacement, kinds=kinds)
        count += redactions
        output.append(
            artifact(file, output_dir, text.encode("utf-8"), "txt", pii_redactions=redactions)
        )
    result = summarize(files, output)
    result.quality["redactions"] = count
    return result


OPERATOR = Operator("text.pii_redact", "text", "privacy", PiiParams, execute)
