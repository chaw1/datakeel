# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Persist isolated question benchmark evidence in the existing eval_runs relation."""

from sqlalchemy import select

from datakeel.core.ask_eval import AskEvalReport
from datakeel.storage.database import Database
from datakeel.storage.harness_rows import EvalRunRow


def save_ask_evaluation(db: Database, report: AskEvalReport) -> AskEvalReport:
    """Append the complete typed provider=ask report without altering benchmark results."""
    with db.session() as session:
        session.add(
            EvalRunRow(
                id=report.id,
                provider=report.provider,
                suite_digest=report.suite_digest,
                created_at=report.created_at.timestamp(),
                payload=report.model_dump(mode="json"),
            )
        )
        session.commit()
    return report


def list_ask_evaluations(db: Database) -> list[AskEvalReport]:
    """Decode only question benchmark reports in deterministic newest-first order."""
    with db.session() as session:
        rows = session.scalars(
            select(EvalRunRow)
            .where(EvalRunRow.provider == "ask")
            .order_by(EvalRunRow.created_at.desc(), EvalRunRow.id.desc())
        )
        return [AskEvalReport.model_validate(row.payload) for row in rows]
