# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Committed extraction accounting derived directly from COMPLETE event facts."""

from datakeel.core.evidence_execution import EvidenceRunReport, OperatorExtractionReport
from datakeel.storage.database import Database
from datakeel.storage.events import all_events


def extraction_report(db: Database, task_id: str) -> EvidenceRunReport:
    """Aggregate only committed extraction nodes for the requested durable task."""
    with db.session() as session:
        operators = tuple(
            OperatorExtractionReport(operator=event.operator, **event.quality)
            for event in all_events(session)
            if event.event_type == "COMPLETE"
            and "knowledge_bundle" in event.params
            and event.source_ref == task_id
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
