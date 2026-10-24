# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Concurrent graph publishers keep association refresh in the shared catalog lock order."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from typing import TYPE_CHECKING

from sqlalchemy import delete, text

from datakeel.core.evidence_drafts import ObservationDraft
from datakeel.core.kg_execution import KGCompletion
from datakeel.core.kg_product import ProductExtraction
from datakeel.storage.catalog_store import publish_snapshot
from datakeel.storage.evidence_rows import AssertionRow
from datakeel.storage.evidence_store import record_extraction_in_session
from datakeel.storage.kg_publication import publish_completion
from datakeel.storage.kg_store import get_job
from datakeel.storage.link_context import read_link_graphs
from datakeel.storage.link_queries import list_links
from tests.storage.link_helpers import seed_link_graph, table_snapshot

if TYPE_CHECKING:
    import pytest
    from sqlalchemy.orm import Session

    from datakeel.core.evidence_cache import KnowledgeBundle
    from datakeel.core.models import LineageEvent
    from datakeel.storage.database import Database


def _fresh_completions(db: Database) -> tuple[KGCompletion, ...]:
    for dataset in ("first", "second"):
        seed_link_graph(db, dataset=dataset)
    with db.session() as session:
        graphs = read_link_graphs(session)
        session.execute(delete(AssertionRow))
        session.commit()
    return tuple(
        KGCompletion(
            run=get_job(db, f"run-doc-{graph.dataset_id}-v1-sales table").run,
            products=ProductExtraction(
                entities=graph.entities,
                drafts=tuple(
                    ObservationDraft.model_validate(
                        assertion.model_dump(include=set(ObservationDraft.model_fields))
                    )
                    for assertion in graph.assertions
                ),
            ),
        )
        for graph in graphs
    )


def test_parallel_dataset_publications_finish_with_current_links(
    db: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two initial dataset publications cannot deadlock upgrading their lineage write locks."""
    publish_snapshot(db, table_snapshot())
    completions = _fresh_completions(db)
    barrier = Barrier(2)
    unsafe_overlap = Barrier(2)

    def interleaved_record(
        session: Session, event: LineageEvent, bundle: KnowledgeBundle | None = None
    ) -> LineageEvent:
        locked = db.sqlite or session.scalar(
            text(
                "SELECT EXISTS (SELECT 1 FROM pg_locks WHERE pid = pg_backend_pid() "
                "AND relation = 'lineage_events'::regclass AND granted "
                "AND mode = 'ShareRowExclusiveLock')"
            )
        )
        result = record_extraction_in_session(session, event, bundle)
        if not locked:
            unsafe_overlap.wait(timeout=10)
        return result

    monkeypatch.setattr(
        "datakeel.storage.kg_publication.record_extraction_in_session", interleaved_record
    )

    def publish(completion: KGCompletion) -> None:
        barrier.wait(timeout=10)
        with db.session() as session:
            db.lock_writes(session)
            publish_completion(session, completion, completion.run.task_id or "")
            session.commit()

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(publish, completion) for completion in completions]
        for future in futures:
            future.result(timeout=30)
    assert len(list_links(db)) == 2
