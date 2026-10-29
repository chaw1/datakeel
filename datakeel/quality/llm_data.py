# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Map recorded training signals onto existing quality dimensions without changing weights."""

from collections import Counter

from pydantic import Field

from datakeel.core.llm_data_models import TrainingReport
from datakeel.core.models import BoundaryModel, FileItem

_STRUCTURE = frozenset(
    {
        "format_error",
        "line_too_large",
        "role_order",
        "missing_final_assistant",
        "empty_turn",
        "empty_prompt",
        "unclosed_code_fence",
        "token_limit",
        "chosen_empty",
    }
)
_DUPLICATES = frozenset(
    {"exact_duplicate", "near_duplicate", "preference_identical", "preference_near_identical"}
)


class TrainingAssessment(BoundaryModel):
    """Aggregate recorded row counts with conservative per-dimension affected fractions."""

    records: int = 0
    issue_counts: dict[str, int] = Field(default_factory=dict)
    scores: dict[str, float] = Field(default_factory=dict)


def assess_training(files: list[FileItem]) -> TrainingAssessment:
    """Penalize only files with recorded offline training evidence; images are unchanged."""
    reports = tuple(
        TrainingReport.model_validate(value)
        for file in files
        if file.modality != "image"
        and isinstance(value := file.metadata.get("training_quality"), dict)
    )
    records = sum(report.records for report in reports)
    counts: Counter[str] = Counter()
    for report in reports:
        counts.update(report.issue_counts)
    if not records:
        return TrainingAssessment()
    # Max avoids counting a row twice when several overlapping rules describe one defect.
    # Uniqueness uses disjoint exact/near duplicate records and preference-pair defects.
    structure = max((counts[code] for code in _STRUCTURE), default=0)
    duplicates = min(records, sum(counts[code] for code in _DUPLICATES))
    consistency = max(
        (count for code, count in counts.items() if code not in _DUPLICATES), default=0
    )
    return TrainingAssessment(
        records=records,
        issue_counts=dict(counts),
        scores={
            "completeness": 100 * (1 - min(records, structure) / records),
            "consistency": 100 * (1 - min(records, consistency) / records),
            "uniqueness": 100 * (1 - duplicates / records),
        },
    )
