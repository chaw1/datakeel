# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Object selections bind current facts, source versions, and disposition revisions."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pydantic import JsonValue

    from datakeel.storage.database import Database
    from datakeel.storage.views import DatasetView

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from datakeel.core.errors import NotFoundError
from datakeel.ontology.models import ObjectSet
from datakeel.storage.database import DatasetRow, VersionRow
from datakeel.storage.file_state import FileStateRow
from datakeel.storage.object_queries import evaluate, evaluate_in_session
from datakeel.storage.task_queue import DatabaseQueue
from datakeel.worker.runner import run_worker


def test_default_file_selection_when_pipeline_runs_preserves_source_assets(
    db: Database, dataset: DatasetView
) -> None:
    """Verify default file selection when pipeline runs preserves source assets."""
    source = evaluate(db, ObjectSet(dataset_id=dataset.id))
    DatabaseQueue(db).submit(dataset.id, "processed")
    run_worker(db, once=True)
    assert evaluate(db, ObjectSet(dataset_id=dataset.id)).state_digest == source.state_digest
    artifacts = evaluate(db, ObjectSet(object_type="artifact", dataset_id=dataset.id))
    assert len(artifacts.objects) < len(source.objects)


def test_quality_threshold_when_source_empty_selects_only_zero_scored_file(
    db: Database, dataset: DatasetView
) -> None:
    """Verify quality threshold when source empty selects only zero scored file."""
    selected = evaluate(db, ObjectSet(dataset_id=dataset.id, quality_max=0))
    assert [item.properties["filename"] for item in selected.objects] == ["empty.txt"]


def test_file_quality_when_recorded_short_text_caps_score_by_measurement(
    db: Database, dataset: DatasetView
) -> None:
    """Verify file quality when recorded short text caps score by measurement."""
    with db.session() as session:
        version = session.scalar(select(VersionRow).where(VersionRow.dataset_id == dataset.id))
        assert version is not None
        version.manifest = [
            {
                **item,
                "metadata": {
                    **item["metadata"],
                    "text_quality": {"characters": 3, "printable_ratio": 0.5},
                },
            }
            if item["filename"] == "short.txt"
            else item
            for item in version.manifest
        ]
        session.commit()
    selected = evaluate(db, ObjectSet(dataset_id=dataset.id, quality_min=1, quality_max=60))
    assert [item.properties["quality"] for item in selected.objects] == [15.0]


def test_frozen_manifest_when_state_changes_gets_new_revision_and_digest(
    db: Database, dataset: DatasetView
) -> None:
    """Verify frozen manifest when state changes gets new revision and digest."""
    before = evaluate(db, ObjectSet(dataset_id=dataset.id))
    target = before.objects[0]
    with db.session() as session:
        session.add(
            FileStateRow(
                dataset_id=dataset.id,
                file_id=target.asset_ref.asset_id,
                quarantined=True,
                revision=1,
            )
        )
        session.commit()
    after = evaluate(db, before.query)
    assert before.state_digest != after.state_digest
    assert after.objects[0].state_revision == 1


def test_deleted_file_when_normal_query_omits_it_but_explicit_query_keeps_it(
    db: Database, dataset: DatasetView
) -> None:
    """Verify deleted file when normal query omits it but explicit query keeps it."""
    before = evaluate(db, ObjectSet(dataset_id=dataset.id))
    with db.session() as session:
        session.add(
            FileStateRow(
                dataset_id=dataset.id,
                file_id=before.objects[0].asset_ref.asset_id,
                deleted=True,
                revision=1,
            )
        )
        session.commit()
    assert len(evaluate(db, before.query).objects) == 2
    assert len(evaluate(db, before.query.model_copy(update={"include_deleted": True})).objects) == 3


def test_query_limit_when_more_matches_exist_marks_manifest_truncated(
    db: Database, dataset: DatasetView
) -> None:
    """Verify query limit when more matches exist marks manifest truncated."""
    value = evaluate(db, ObjectSet(dataset_id=dataset.id, limit=1))
    assert value.truncated is True
    assert len(value.objects) == 1
    assert value.total_bytes == sum(item.size for item in value.objects)


def test_version_range_when_time_interval_excludes_source_returns_empty(
    db: Database, dataset: DatasetView
) -> None:
    """Verify version range when time interval excludes source returns empty."""
    future = datetime.now(UTC) + timedelta(days=1)
    assert evaluate(db, ObjectSet(dataset_id=dataset.id, created_after=future)).objects == []


def test_version_range_when_explicit_source_and_upper_bound_keeps_source(
    db: Database, dataset: DatasetView
) -> None:
    """Verify version range when explicit source and upper bound keeps source."""
    first = evaluate(db, ObjectSet(dataset_id=dataset.id)).objects[0]
    query = ObjectSet(
        dataset_id=dataset.id,
        version_ids=[first.asset_ref.version],
        created_before=datetime.now(UTC),
    )
    assert len(evaluate(db, query).objects) == 3


def test_task_projection_when_task_created_uses_persisted_task_identity(
    db: Database, dataset: DatasetView
) -> None:
    """Verify task projection when task created uses persisted task identity."""
    task_id = DatabaseQueue(db).submit(dataset.id, "task-object")
    manifest = evaluate(db, ObjectSet(object_type="task", dataset_id=dataset.id))
    assert manifest.objects[0].asset_ref.asset_id == task_id


def test_query_when_dataset_missing_raises_domain_not_found(db: Database) -> None:
    """Verify query when dataset missing raises domain not found."""
    with pytest.raises(NotFoundError, match="Dataset not found"):
        evaluate(db, ObjectSet(dataset_id="missing"))


def test_query_in_session_when_called_observes_uncommitted_state(
    db: Database, dataset: DatasetView
) -> None:
    """Verify query in session when called observes uncommitted state."""
    with db.session() as session:
        row = session.get(DatasetRow, dataset.id)
        assert row is not None
        row.name = "changed inside transaction"
        session.flush()
        result = evaluate_in_session(
            session, ObjectSet(object_type="dataset", dataset_id=dataset.id)
        )
        assert result.objects[0].properties["name"] == row.name
        session.rollback()


@pytest.mark.parametrize(
    ("field", "operator", "value", "count"),
    [
        ("filename", "eq", "empty.txt", 1),
        ("quality", "eq", 0, 1),
        ("filename", "ne", "empty.txt", 2),
        ("size", "gt", 0, 2),
        ("size", "gte", 0, 3),
        ("size", "lt", 1, 1),
        ("size", "lte", 0, 1),
        ("filename", "contains", "empty", 1),
        ("filename", "in", ["empty.txt", "short.txt"], 2),
        ("missing.field", "eq", None, 0),
        ("quarantined", "eq", 0, 0),
        ("filename", "lt", 1, 0),
        ("quarantined", "gt", 0, 0),
        ("metadata.semantic.modality", "eq", "text", 3),
    ],
)
def test_property_predicate_when_evaluated_preserves_declared_operator(
    db: Database, dataset: DatasetView, field: str, operator: str, value: JsonValue, count: int
) -> None:
    """Verify property predicate when evaluated preserves declared operator."""
    query = ObjectSet.model_validate(
        {
            "dataset_id": dataset.id,
            "filters": [{"field": field, "operator": operator, "value": value}],
        }
    )
    assert len(evaluate(db, query).objects) == count
