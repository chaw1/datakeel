# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Expose decoded video stream properties as typed JSON metadata."""

from pathlib import Path

from datakeel.core.errors import ValidationError
from datakeel.core.models import FileItem
from datakeel.operators.base import EmptyParams, Operator, OperatorResult, summarize
from datakeel.operators.media.probe_annotation import annotate_probe
from datakeel.operators.media.tools import probe_file


def execute(files: list[FileItem], _output_dir: Path, _params: EmptyParams) -> OperatorResult:
    """Inspect duration, codec, frame rate, rotation and audio stream count."""
    output: list[FileItem] = []
    for file in files:
        probe = probe_file(file)
        if not probe.width or not probe.height:
            msg = "Recording contains no video stream"
            raise ValidationError(msg)
        output.append(annotate_probe(file, probe))
    return summarize(files, output)


OPERATOR = Operator("video.probe", "video", "inspection", EmptyParams, execute)
