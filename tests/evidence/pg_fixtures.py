# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Generated PG publication fixtures, preserving the existing fix2 tests byte for byte."""

from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING

from sqlalchemy import event as sql_event
from sqlalchemy import select

from datakeel.core.evidence_cache import KnowledgeBundle
from datakeel.core.models import LineageEvent, new_id
from datakeel.dataset_store.rows import EventRow
from datakeel.storage import evidence_store
from tests.evidence.helpers import extraction_event, fixture_bundle
from tests.evidence.vector_helpers import vector_dataset, vector_run
from tests.pg_evidence_helpers import require_postgres

if TYPE_CHECKING:
    from collections.abc import Callable, Generator
    from pathlib import Path

    from datakeel.storage.database import Database


def fresh_publication(
    db: Database, tmp_path: Path
) -> Callable[[], tuple[LineageEvent, KnowledgeBundle]]:
    """Clone generated fake-vector provenance with new identities and the same cache key."""
    require_postgres(db)
    run = vector_run(db, vector_dataset(db, tmp_path / "inputs"))
    assert run.state == "COMPLETED", run.error
    with db.session() as session:
        template = next(
            LineageEvent.model_validate(row.payload)
            for row in session.scalars(select(EventRow))
            if row.payload.get("operator") == "evidence.vector_embed"
        )
    base = evidence_store.validated_bundle(template)

    def clone() -> tuple[LineageEvent, KnowledgeBundle]:
        identifier = new_id()
        event = template.model_copy(
            update={
                "event_id": identifier,
                "idempotency_key": identifier,
                "source_ref": identifier,
                "params": {
                    **{
                        key: value
                        for key, value in template.params.items()
                        if key != "knowledge_bundle"
                    },
                    "run_id": identifier,
                },
            }
        )
        return event, base.model_copy(
            update={"run_id": identifier, "invalidations": (), "prior_cache_event_ids": ()}
        )

    return clone


def batch_event(size: int, run: str = "batch") -> LineageEvent:
    """Build an ordinary generated extraction with the existing batching fixture shape."""
    event = extraction_event(run)
    template = fixture_bundle(event)
    assertion = template.assertions[0]
    entry = template.cache_entries[0]
    subjects = [entry.subject.model_copy(update={"asset_id": f"image-{i}"}) for i in range(size)]
    assertions = tuple(
        assertion.model_copy(
            update={
                "id": f"assertion-{run}-{i}",
                "subject": subject,
                "anchors": (assertion.anchors[0].model_copy(update={"asset_ref": subject}),),
            }
        )
        for i, subject in enumerate(subjects)
    )
    bundle = KnowledgeBundle(
        run_id=run,
        assertions=assertions,
        cache_entries=tuple(
            entry.model_copy(update={"subject": item.subject, "assertion_ids": (item.id,)})
            for item in assertions
        ),
    )
    return event.model_copy(
        update={
            "inputs": subjects,
            "params": {"run_id": run, "knowledge_bundle": bundle.model_dump(mode="json")},
        }
    )


@contextmanager
def statements(db: Database) -> Generator[list[str]]:
    """Record actual fixture SQL without changing dispatch or execution."""
    statements: list[str] = []

    def track(
        connection: object,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,  # noqa: FBT001  # SQLAlchemy event callback signature.
    ) -> None:
        statements.append(statement)

    sql_event.listen(db.engine, "before_cursor_execute", track)
    try:
        yield statements
    finally:
        sql_event.remove(db.engine, "before_cursor_execute", track)
