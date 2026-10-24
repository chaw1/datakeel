# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Persist and query immutable graph evaluations without changing earlier evaluation kinds."""

from sqlalchemy import select

from datakeel.core.errors import ConflictError, NotFoundError, ValidationError
from datakeel.core.kg_eval_models import KGEvalReport
from datakeel.storage.database import Database
from datakeel.storage.kg_eval_rows import KGEvalRunRow

MAX_EVALUATION_HISTORY = 1000


def save_evaluation(db: Database, report: KGEvalReport) -> KGEvalReport:
    """Persist one report transactionally; retrying its exact identity is idempotent."""
    with db.session() as session:
        previous = session.get(KGEvalRunRow, report.id)
        if previous is not None:
            if KGEvalReport.model_validate(previous.payload) != report:
                msg = "An evaluation identity cannot be replaced with different evidence"
                raise ConflictError(msg)
            return report
        session.add(
            KGEvalRunRow(
                id=report.id,
                profile=report.profile,
                model=report.model,
                suite_digest=report.suite_digest,
                payload=report.model_dump(mode="json"),
                created_at=report.created_at.timestamp(),
            )
        )
        session.commit()
    return report


def list_evaluations(db: Database, limit: int = 100) -> tuple[KGEvalReport, ...]:
    """Return bounded recent reports with complete recording and production-path metrics."""
    if not 1 <= limit <= MAX_EVALUATION_HISTORY:
        msg = f"Evaluation history limit must be between 1 and {MAX_EVALUATION_HISTORY}"
        raise ValidationError(msg)
    with db.session() as session:
        rows = session.scalars(
            select(KGEvalRunRow)
            .order_by(KGEvalRunRow.created_at.desc(), KGEvalRunRow.id.desc())
            .limit(limit)
        )
        return tuple(KGEvalReport.model_validate(row.payload) for row in rows)


def get_evaluation(db: Database, evaluation_id: str) -> KGEvalReport:
    """Return one immutable report or an explicit missing-resource failure."""
    with db.session() as session:
        row = session.get(KGEvalRunRow, evaluation_id)
        if row is None:
            msg = "Knowledge-graph evaluation was not found"
            raise NotFoundError(msg)
        return KGEvalReport.model_validate(row.payload)
