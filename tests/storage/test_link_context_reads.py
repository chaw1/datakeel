# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Bound association reads to current graph facts before ORM materialization."""

from collections import Counter

from sqlalchemy import event, insert
from sqlalchemy.orm import Session

from datakeel.core.evidence_models import (
    Assertion,
    EvidenceAnchor,
    EvidenceValue,
    ExtractorRef,
    Whole,
)
from datakeel.core.models import AssetRef, LineageEvent
from datakeel.storage.catalog_store import publish_snapshot
from datakeel.storage.database import Database, EventRow
from datakeel.storage.events import append_event
from datakeel.storage.evidence_rows import AssertionRow
from datakeel.storage.link_queries import read_link_context
from tests.storage.link_helpers import seed_link_graph, table_snapshot


def _add_unrelated_facts(db: Database) -> None:
    source = LineageEvent(idempotency_key="unrelated-ask", operator="evidence.ask")
    subject = AssetRef(asset_type="question", asset_id="question", version="question")
    assertion = Assertion(
        subject=subject,
        predicate="ask.unanswerable",
        object=EvidenceValue(concept="metric", value="unknown"),
        anchors=(EvidenceAnchor(asset_ref=subject, content_revision="a" * 64, selector=Whole()),),
        extractor=ExtractorRef(id="evidence.ask", version="1"),
        run_id="unrelated",
        producer_event_id=source.event_id,
    )
    with db.session() as session:
        append_event(session, source)
        session.execute(
            insert(AssertionRow),
            [
                {
                    "id": f"unrelated-{index}",
                    "subject_id": subject.asset_id,
                    "predicate": assertion.predicate,
                    "producer_event_id": source.event_id,
                    "payload": assertion.model_copy(update={"id": f"unrelated-{index}"}).model_dump(
                        mode="json"
                    ),
                    "status": "candidate",
                    "active": True,
                }
                for index in range(5000)
            ],
        )
        session.commit()


def _loaded_rows(db: Database) -> Counter[str]:
    loaded: Counter[str] = Counter()

    def count_rows(_session: Session, row: object) -> None:
        if isinstance(row, (AssertionRow, EventRow)):
            loaded[type(row).__name__] += 1

    event.listen(Session, "loaded_as_persistent", count_rows)
    try:
        assert read_link_context(db).assertions
    finally:
        event.remove(Session, "loaded_as_persistent", count_rows)
    return loaded


def test_link_context_load_count_ignores_five_thousand_unrelated_assertions(db: Database) -> None:
    """Unrelated audit assertions and their events never enter the graph reader's ORM results."""
    seed_link_graph(db)
    publish_snapshot(db, table_snapshot())
    before = _loaded_rows(db)
    _add_unrelated_facts(db)
    assert before["AssertionRow"] > 0
    assert before["EventRow"] > 0
    assert _loaded_rows(db) == before
