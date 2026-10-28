# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Frozen documentation history, publication and stale overlays share storage transactions."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from datakeel.core.errors import ConflictError, NotFoundError, ValidationError
from datakeel.storage.database import DatasetRow, VersionRow
from datakeel.storage.datasheet_rows import DatasheetRow
from datakeel.storage.datasheet_store import (
    compare_documents,
    get_document,
    list_documents,
    publish_in_session,
    save_document,
    save_in_session,
)
from tests.storage.datasheet_helpers import dataset_versions, saved_draft

if TYPE_CHECKING:
    from datakeel.storage.database import Database


def test_saved_old_document_is_stale_without_recomputing_its_frozen_facts(db: Database) -> None:
    """Old prose and facts survive metadata changes, while expiry follows new manifest versions."""
    dataset_id, before_id, after_id = dataset_versions(db)
    before = save_document(db, saved_draft(db, dataset_id, before_id))
    after = save_document(db, saved_draft(db, dataset_id, after_id))
    assert before.stale
    assert not after.stale
    assert save_document(db, before) == before
    with db.session() as session:
        dataset = session.get(DatasetRow, dataset_id)
        assert dataset is not None
        dataset.metadata_values = {"description": "Changed later"}
        session.add(VersionRow(dataset_id=dataset_id, created_at=500, manifest=[]))
        session.commit()
    assert get_document(db, after.id).stale
    assert get_document(db, before.id).facts == before.facts
    assert list_documents(db, dataset_id) == (get_document(db, after.id), before)
    assert list_documents(db, dataset_id, before_id) == (before,)
    assert compare_documents(db, before.id, before.id).changes == ()
    comparison = compare_documents(db, before.id, after.id)
    assert comparison.changes
    assert "composition" in comparison.changed_chapters
    kinds = {change.fact_id: change.kind for change in comparison.changes}
    count = next(fact for fact in after.facts if fact.field == "manifest.file_count")
    assert kinds[count.id] == "changed"
    assert "changed" in kinds.values()


def test_stored_identity_rejects_replacement_and_new_draft_cannot_start_published(
    db: Database,
) -> None:
    """Never overwrite checked text and never bypass the publication transition at insertion."""
    dataset_id, before_id, _ = dataset_versions(db)
    document = save_document(db, saved_draft(db, dataset_id, before_id))
    with pytest.raises(ConflictError, match="immutable content"):
        save_document(db, document.model_copy(update={"language": "en"}))
    with pytest.raises(ValidationError, match="unpublished draft"):
        save_document(db, document.model_copy(update={"id": "new-published", "published": True}))
    with db.session() as session:
        row = session.get(DatasheetRow, document.id)
        assert row is not None
        assert "stale" not in row.payload
        assert "published" not in row.payload


def test_publication_and_save_participate_in_caller_transaction(db: Database) -> None:
    """Roll back both transitions when an owning action transaction does not commit."""
    dataset_id, before_id, _ = dataset_versions(db)
    draft = saved_draft(db, dataset_id, before_id)
    with db.session() as session:
        save_in_session(session, draft)
        session.rollback()
    with pytest.raises(NotFoundError):
        get_document(db, draft.id)
    save_document(db, draft)
    with db.session() as session:
        assert publish_in_session(session, draft.id).published
        session.rollback()
    assert not get_document(db, draft.id).published
    with db.session() as session:
        assert publish_in_session(session, draft.id).published
        session.commit()
    assert get_document(db, draft.id).published


def test_comparison_reports_same_identity_value_changes_and_cross_dataset_is_rejected(
    db: Database,
) -> None:
    """Compare saved values rather than recording times or unrelated dataset histories."""
    dataset_id, before_id, _ = dataset_versions(db)
    before = save_document(db, saved_draft(db, dataset_id, before_id))
    owner = next(fact for fact in before.facts if fact.field == "metadata.creator")
    after = before.model_copy(
        update={
            "id": "revised-draft",
            "facts": tuple(
                fact.model_copy(update={"value": "Revised creator"})
                if fact.id == owner.id
                else fact
                for fact in before.facts
            ),
        }
    )
    save_document(db, after)
    changes = compare_documents(db, before.id, after.id).changes
    assert len(changes) == 1
    assert changes[0].kind == "changed"
    assert changes[0].before == "Fixture creator"
    assert changes[0].after == "Revised creator"
    other_dataset, other_version, _ = dataset_versions(db)
    other = save_document(db, saved_draft(db, other_dataset, other_version))
    with pytest.raises(ValidationError, match="same dataset"):
        compare_documents(db, before.id, other.id)


def test_missing_document_and_invalid_history_scope_are_explicit_errors(db: Database) -> None:
    """Avoid returning unrelated history when a selected document or dataset does not exist."""
    dataset_id, _, _ = dataset_versions(db)
    with pytest.raises(NotFoundError):
        get_document(db, "missing")
    with pytest.raises(NotFoundError):
        list_documents(db, "missing")
    with pytest.raises(NotFoundError):
        list_documents(db, dataset_id, "missing")
