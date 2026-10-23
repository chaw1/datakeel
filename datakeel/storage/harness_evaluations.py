# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Persist typed evaluation evidence and compare it with the previous run."""

from sqlalchemy import select

from datakeel.core.harness_eval import EvalReport
from datakeel.storage.budget_accounts import lock_budget
from datakeel.storage.database import Database
from datakeel.storage.harness_rows import EvalRunRow


def save_evaluation(db: Database, report: EvalReport) -> EvalReport:
    """Store one immutable run with deltas against the previous provider run."""
    with db.session() as session:
        lock_budget(db, session)
        row = session.scalar(
            select(EvalRunRow)
            .where(EvalRunRow.provider == report.provider)
            .order_by(EvalRunRow.created_at.desc(), EvalRunRow.id.desc())
            .limit(1)
        )
        if row is not None:
            previous = EvalReport.model_validate(row.payload)
            report = report.model_copy(
                update={
                    "previous_id": previous.id,
                    "previous_suite_digest": previous.suite_digest,
                    "passed_delta": report.passed - previous.passed,
                    "token_delta": report.total_tokens - previous.total_tokens,
                    "cost_delta": report.total_cost_usd - previous.total_cost_usd,
                }
            )
        session.add(
            EvalRunRow(
                id=report.id,
                provider=report.provider,
                suite_digest=report.suite_digest,
                payload=report.model_dump(mode="json"),
            )
        )
        session.commit()
        return report


def list_evaluations(db: Database) -> list[EvalReport]:
    """Return complete stored reports in reverse chronological order."""
    with db.session() as session:
        rows = session.scalars(
            select(EvalRunRow)
            .where(EvalRunRow.provider.not_in(["evidence", "ask"]))
            .order_by(EvalRunRow.created_at.desc())
        )
        return [EvalReport.model_validate(row.payload) for row in rows]
