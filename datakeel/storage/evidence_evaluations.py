# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Persist evidence reports beside agent evaluations without changing their HTTP schema."""

from sqlalchemy import select

from datakeel.core.evidence_eval import EvidenceEvalReport
from datakeel.ontology.models import FrozenManifest, ObjectSet
from datakeel.storage.database import Database
from datakeel.storage.evidence_snapshot import read_snapshot
from datakeel.storage.harness_rows import EvalRunRow
from datakeel.storage.object_queries import evaluate_in_session


def benchmark_selections(
    db: Database, queries: tuple[ObjectSet, ...]
) -> tuple[FrozenManifest, ...]:
    """Run both query expressions against one consistent evidence snapshot."""
    with db.session() as session:
        snapshot = read_snapshot(
            session, include_peer_splits=any(query.has_near_duplicate_in for query in queries)
        )
        return tuple(evaluate_in_session(session, query, snapshot) for query in queries)


def save_evidence_evaluation(db: Database, report: EvidenceEvalReport) -> EvidenceEvalReport:
    """Append a typed provider=evidence record to the existing evaluation relation."""
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


def list_evidence_evaluations(db: Database) -> list[EvidenceEvalReport]:
    """Read evidence reports without attempting to decode unrelated agent reports."""
    with db.session() as session:
        rows = session.scalars(
            select(EvalRunRow)
            .where(EvalRunRow.provider == "evidence")
            .order_by(EvalRunRow.created_at.desc(), EvalRunRow.id.desc())
        )
        return [EvidenceEvalReport.model_validate(row.payload) for row in rows]
