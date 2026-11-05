# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Read typed fake task status from committed events and durable attempt audits."""

from sqlalchemy import select

from datakeel.core.vector_models import VectorCounts
from datakeel.core.vector_results import VectorNodeReport, VectorTaskReport
from datakeel.dataset_store.rows import EventRow
from datakeel.storage.database import Database
from datakeel.storage.evidence_runs import extraction_report
from datakeel.storage.vector_budget import list_vector_attempts
from datakeel.storage.vector_completion import has_vector_work
from datakeel.worker_store.rows import TaskRow


def vector_task_report(db: Database, task_id: str) -> VectorTaskReport | None:
    """Return no count for unpublished failure products; keep attempts readable after failure."""
    with db.session() as session:
        task = session.scalar(select(TaskRow).where(TaskRow.id == task_id))
        if task is None or not (
            has_vector_work(session, task_id, task)
            or (task.error and task.error.startswith(("vector_", "VectorError: vector_")))
        ):
            return None
        nodes = tuple(
            item.vector
            for item in extraction_report(db, task_id).operators
            if item.vector is not None
        )
        failures = tuple(
            VectorNodeReport(
                status="failed",
                reason=str(row.payload["quality"].get("vector_failure_reason")),
                counts=VectorCounts.model_validate(row.payload["quality"]["vector_failure_counts"]),
            )
            for row in session.scalars(
                select(EventRow).where(EventRow.payload["source_ref"].as_string() == task_id)
            )
            if "vector_failure_counts" in row.payload.get("quality", {})
        )
        nodes += failures
        status = (
            "failed"
            if task.state == "FAILED"
            else "cancelled"
            if task.state == "CANCELLED"
            else "partial_success"
            if any(node.status == "partial_success" for node in nodes)
            else "success"
            if task.state == "COMPLETED"
            else "pending"
        )
        return VectorTaskReport(
            status=status,
            reason=task.error.removeprefix("VectorError: ") if task.error else None,
            nodes=nodes,
            attempts=list_vector_attempts(db, task_id),
        )
