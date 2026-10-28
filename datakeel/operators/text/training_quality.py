# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Expose the offline JSONL governance engine as a typed built-in analysis operator."""

from pathlib import Path
from typing import cast

from pydantic import field_validator

from datakeel.core.llm_data_models import TrainingConfig, TrainingSource
from datakeel.core.models import FileItem
from datakeel.operators.base import Operator, OperatorResult, Params, annotate, summarize


class TrainingQualityParams(Params, TrainingConfig):
    """Freeze the same rule configuration at pipeline and interactive boundaries."""

    @field_validator("refusal_phrases", "safety_terms", mode="before")
    @classmethod
    def json_word_lists(cls, value: object) -> object:
        """Accept JSON arrays while retaining strict element and numeric validation."""
        return tuple(cast("list[object]", value)) if isinstance(value, list) else value


def execute(
    files: list[FileItem], _output_dir: Path, params: TrainingQualityParams
) -> OperatorResult:
    """Annotate JSONL sources while leaving ordinary text files for their existing checks."""
    # Registry loading eagerly imports operators; resolve the domain after registration.
    from datakeel.llm_data import analyze_sources  # noqa: PLC0415

    output: list[FileItem] = []
    for file in files:
        if Path(file.filename).suffix.casefold() not in {".jsonl", ".ndjson"}:
            output.append(file)
            continue
        source = TrainingSource(file_id=file.id, path=file.path, filename=file.filename)
        report = analyze_sources((source,), TrainingConfig.model_validate(params.model_dump()))
        output.append(annotate(file, training_quality=report.model_dump(mode="json")))
    return summarize(files, output)


OPERATOR = Operator("text.training_quality", "text", "quality", TrainingQualityParams, execute)
