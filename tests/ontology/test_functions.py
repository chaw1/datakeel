# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Read functions validate schemas and retain explicit audit asset identities."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datakeel.storage.database import Database
    from datakeel.storage.views import DatasetView

import pytest
from pydantic import ValidationError

from datakeel.core.errors import NotFoundError
from datakeel.core.models import JsonDocument
from datakeel.ontology.functions import invoke_function
from datakeel.ontology.models import ObjectSet
from datakeel.storage.file_state import FileStateRow
from datakeel.storage.object_queries import evaluate
from datakeel.storage.task_queue import DatabaseQueue


def test_list_datasets_when_called_returns_dataset_asset_refs(
    db: Database, dataset: DatasetView
) -> None:
    """Verify list datasets when called returns dataset asset refs."""
    result = invoke_function(db, "list_datasets", JsonDocument({}))
    assert [ref.asset_id for ref in result.asset_refs] == [dataset.id]


def test_search_files_when_multiple_filters_used_returns_only_matching_assets(
    db: Database, dataset: DatasetView
) -> None:
    """Verify search files when multiple filters used returns only matching assets."""
    manifest = evaluate(db, ObjectSet(dataset_id=dataset.id, quality_max=0))
    with db.session() as session:
        session.add(
            FileStateRow(
                dataset_id=dataset.id,
                file_id=manifest.objects[0].asset_ref.asset_id,
                quarantined=True,
                revision=1,
            )
        )
        session.commit()
    result = invoke_function(
        db,
        "search_files",
        JsonDocument(
            {
                "dataset_id": dataset.id,
                "modality": "text",
                "quality_max": 60,
                "quarantined": True,
                "path": "empty",
            }
        ),
    )
    assert [ref.asset_id for ref in result.asset_refs] == [manifest.objects[0].asset_ref.asset_id]


def test_search_files_when_no_match_retains_target_dataset_identity_for_audit(
    db: Database, dataset: DatasetView
) -> None:
    """Verify search files when no match retains target dataset identity for audit."""
    result = invoke_function(
        db, "search_files", JsonDocument({"dataset_id": dataset.id, "modality": "audio"})
    )
    assert result.asset_refs[0].asset_id == dataset.id


@pytest.mark.parametrize("name", ["get_quality", "get_report"])
def test_dataset_read_when_requested_retains_dataset_reference(
    db: Database, dataset: DatasetView, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    """Verify dataset read when requested retains dataset reference."""
    monkeypatch.delenv("DATAKEEL_LLM_URL", raising=False)
    result = invoke_function(db, name, JsonDocument({"dataset_id": dataset.id}))
    assert result.asset_refs[0].asset_id == dataset.id
    assert result.data


def test_lineage_read_when_requested_returns_related_asset_references(
    db: Database, dataset: DatasetView
) -> None:
    """Verify lineage read when requested returns related asset references."""
    result = invoke_function(db, "get_lineage", JsonDocument({"asset_id": dataset.id}))
    assert dataset.id in {ref.asset_id for ref in result.asset_refs}


def test_lineage_read_when_unknown_asset_preserves_requested_identity(db: Database) -> None:
    """Verify lineage read when unknown asset preserves requested identity."""
    result = invoke_function(db, "get_lineage", JsonDocument({"asset_id": "unknown"}))
    assert result.asset_refs[0].asset_id == "unknown"


def test_task_read_when_requested_retains_task_identity(db: Database, dataset: DatasetView) -> None:
    """Verify task read when requested retains task identity."""
    task_id = DatabaseQueue(db).submit(dataset.id, "read-task")
    result = invoke_function(db, "get_task", JsonDocument({"task_id": task_id}))
    assert result.asset_refs[0].asset_id == task_id


def test_function_when_unknown_name_is_rejected_without_execution(db: Database) -> None:
    """Verify function when unknown name is rejected without execution."""
    with pytest.raises(NotFoundError, match="Unknown read function"):
        invoke_function(db, "unknown", JsonDocument({}))


def test_function_when_undeclared_argument_supplied_rejects_input(db: Database) -> None:
    """Verify function when undeclared argument supplied rejects input."""
    with pytest.raises(ValidationError, match="extra_forbidden"):
        invoke_function(db, "list_datasets", JsonDocument({"untrusted": True}))
