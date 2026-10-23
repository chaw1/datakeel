# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Normalize supported byte encodings and line endings to UTF-8."""

from pathlib import Path

from datakeel.core.models import FileItem
from datakeel.operators.base import EncodingParams, Operator, OperatorResult, artifact, summarize


def execute(files: list[FileItem], output_dir: Path, params: EncodingParams) -> OperatorResult:
    """Normalize supported byte encodings and line endings to UTF-8."""
    output: list[FileItem] = []
    for file in files:
        content = Path(file.path).read_bytes()
        encoding = "utf-8-sig"
        if content.startswith((b"\xff\xfe", b"\xfe\xff")):
            encoding = "utf-16"
        try:
            text = content.decode(encoding)
        except UnicodeDecodeError:
            encoding = params.fallback
            text = content.decode(encoding)
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        output.append(
            artifact(
                file,
                output_dir,
                text.encode("utf-8"),
                "txt",
                encoding="utf-8",
                source_encoding=encoding,
            )
        )
    return summarize(files, output)


OPERATOR = Operator("text.encoding_fix", "text", "transform", EncodingParams, execute, "io")
