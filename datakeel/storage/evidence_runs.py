# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Committed extraction accounting derived directly from COMPLETE event facts."""

from sqlalchemy import select

from datakeel.core.evidence_execution import EvidenceRunReport, OperatorExtractionReport
from datakeel.storage.database import Database, EventRow


def extraction_report(db: Database, task_id: str) -> EvidenceRunReport:
    """Aggregate only committed extraction nodes for the requested durable task."""
    with db.session() as session:
        statement = select(
            EventRow.payload["operator"].as_string(),
            EventRow.payload["quality"],
            EventRow.payload["params"],
        ).where(
            EventRow.payload["event_type"].as_string() == "COMPLETE",
            EventRow.payload["source_ref"].as_string() == task_id,
        )
        operators = tuple(
            OperatorExtractionReport(operator=operator, **quality)
            for operator, quality, params in session.execute(statement)
            if "knowledge_bundle" in params
        )
    return EvidenceRunReport(
        task_id=task_id,
        operators=operators,
        inputs=sum(item.inputs for item in operators),
        skipped_cached=sum(item.skipped_cached for item in operators),
        extracted=sum(item.extracted for item in operators),
        failed=sum(item.failed for item in operators),
        elapsed_seconds=sum(item.elapsed_seconds for item in operators),
    )
