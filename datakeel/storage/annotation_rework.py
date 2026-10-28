# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Export actionable repair candidates from statistical findings and human inspection errors."""

import csv
import io
import json

from sqlalchemy import select

from datakeel.core.annotation_sampling import (
    AnnotationQualityReport,
    ReworkItem,
    SamplingInspection,
)
from datakeel.storage.annotation_rows import AnnotationInspectionRow
from datakeel.storage.annotation_store import require_batch
from datakeel.storage.database import Database


def rework_items(db: Database, dataset_id: str, batch_id: str) -> tuple[ReworkItem, ...]:
    """Keep suspicion and human-confirmed error provenance distinct in the repair list."""
    with db.session() as session:
        report = AnnotationQualityReport.model_validate(
            require_batch(session, dataset_id, batch_id).report
        )
        result = [
            ReworkItem(
                item_id=finding.finding_id,
                sample_id=finding.sample_id,
                annotator_id=finding.annotator_id,
                code=finding.code,
                reason=finding.reason,
                evidence=finding.evidence,
            )
            for finding in report.result.findings
        ]
        rows = session.scalars(
            select(AnnotationInspectionRow)
            .where(AnnotationInspectionRow.batch_id == batch_id)
            .order_by(AnnotationInspectionRow.created_at, AnnotationInspectionRow.id)
        )
        for row in rows:
            inspection = SamplingInspection.model_validate(row.payload)
            result.extend(
                ReworkItem(
                    item_id=f"{inspection.id}:{check.sample_id}",
                    sample_id=check.sample_id,
                    code="inspection_error",
                    reason=check.reason,
                    evidence=(f"Approved inspection {inspection.id}",),
                    inspection_id=inspection.id,
                )
                for check in inspection.checks
                if check.defective
            )
        return tuple(result)


def _csv_cell(value: str) -> str:
    return "'" + value if value.lstrip().startswith(("=", "+", "-", "@")) else value


def export_rework(db: Database, dataset_id: str, batch_id: str, *, csv_format: bool) -> str:
    """Encode typed repair items as JSON or spreadsheet-safe CSV, retaining every reason."""
    items = rework_items(db, dataset_id, batch_id)
    if not csv_format:
        return json.dumps([item.model_dump(mode="json") for item in items], ensure_ascii=False)
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(
        ["item_id", "sample_id", "annotator_id", "code", "reason", "evidence", "inspection_id"]
    )
    for item in items:
        writer.writerow(
            [
                _csv_cell(value)
                for value in (
                    item.item_id,
                    item.sample_id,
                    item.annotator_id or "",
                    item.code,
                    item.reason,
                    "; ".join(item.evidence),
                    item.inspection_id or "",
                )
            ]
        )
    return output.getvalue()
