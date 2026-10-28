# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Extract typed, version-pinned training governance facts for cited datasheets."""

from sqlalchemy.orm import Session

from datakeel.core.datasheet_models import DatasheetFact
from datakeel.core.training_governance import TrainingGovernanceRun
from datakeel.storage.datasheet_values import make_fact
from datakeel.storage.training_store import version_training_report


def training_facts(session: Session, dataset_id: str, version_id: str) -> tuple[DatasheetFact, ...]:
    """Reuse persisted measurements instead of inferring training statistics from prose."""
    saved = version_training_report(session, dataset_id, version_id)
    if saved is None:
        return ()
    report, row = saved
    measured = TrainingGovernanceRun.model_validate(row.payload).created_at
    counts = report.issue_counts
    denominator = max(1, report.records)
    duplicates = min(
        report.records, counts.get("exact_duplicate", 0) + counts.get("near_duplicate", 0)
    )
    pii = report.pii_records
    values: tuple[tuple[str, object], ...] = (
        ("training.records", report.records),
        ("training.language_distribution", report.languages),
        ("training.deduplication_rate", duplicates / denominator),
        ("training.pii_records", pii),
        ("training.contamination_rate", counts.get("contamination", 0) / denominator),
        ("training.format_error_rate", counts.get("format_error", 0) / denominator),
        ("training.issue_counts", counts),
        ("training.rule_version", report.rule_version),
    )
    return tuple(
        fact
        for field, value in values
        if (
            fact := make_fact(
                "preprocessing", "training_governance", row.id, field, value, measured
            )
        )
        is not None
    )
