# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Version-pinned deterministic documentation cannot read a newer or overlaid manifest."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from datakeel.core.errors import NotFoundError
from datakeel.storage.database import DatasetRow, MetadataChangeRow
from datakeel.storage.datasheet_facts import extract_facts
from datakeel.storage.file_state import FileStateRow
from tests.storage.datasheet_helpers import dataset_versions

if TYPE_CHECKING:
    from datakeel.storage.database import Database


def test_old_version_uses_immutable_manifest_despite_latest_and_file_state(db: Database) -> None:
    """Preserve original file count, composition and quality after newer files and deletion."""
    dataset_id, before_id, after_id = dataset_versions(db)
    with db.session() as session:
        session.add(FileStateRow(dataset_id=dataset_id, file_id="original-file", deleted=True))
        session.commit()
    with db.session() as session:
        before = {fact.field: fact for fact in extract_facts(session, dataset_id, before_id)}
        after = {fact.field: fact for fact in extract_facts(session, dataset_id, after_id)}
    assert before["manifest.file_count"].value == 1
    assert before["manifest.filenames.1"].value == ["original.txt"]
    assert before["manifest.modalities"].value == {"text": 1}
    assert before["manifest.total_bytes"].value == 10
    assert after["manifest.file_count"].value == 2
    assert after["manifest.modalities"].value == {"image": 1, "text": 1}
    assert before["quality.total"].value == 100
    assert before["version.created_at"].recorded_at.timestamp() == 200


def test_fact_identity_stable_for_same_source_field_and_values_are_public(db: Database) -> None:
    """Keep deterministic IDs and omit private storage paths and unrecognized credentials."""
    dataset_id, before_id, _ = dataset_versions(db)
    with db.session() as session:
        first = extract_facts(session, dataset_id, before_id)
        second = extract_facts(session, dataset_id, before_id)
    assert [(fact.id, fact.value) for fact in first] == [(fact.id, fact.value) for fact in second]
    assert len({fact.id for fact in first}) == len(first)
    assert "unmaterialized" not in str(first)


def test_metadata_owner_retains_its_field_audit_timestamp_and_filters_unsafe_values(
    db: Database,
) -> None:
    """Attribute mutable metadata to its audit rather than the selected manifest's timestamp."""
    dataset_id, before_id, _ = dataset_versions(db)
    with db.session() as session:
        dataset = session.get(DatasetRow, dataset_id)
        assert dataset is not None
        dataset.metadata_values = {
            "owner": "Research group",
            "purpose": "Bearer secret-value",
            "password": "do-not-export",
            "description": "",
        }
        session.add(
            MetadataChangeRow(
                dataset_id=dataset_id,
                field="owner",
                before=None,
                after="Research group",
                source="test",
                reason="Assigned",
                occurred_at=400,
            )
        )
        session.commit()
    with db.session() as session:
        facts = {fact.field: fact for fact in extract_facts(session, dataset_id, before_id)}
    assert facts["metadata.owner"].value == "Research group"
    assert facts["metadata.owner"].recorded_at.timestamp() == 400
    assert "metadata.purpose" not in facts
    assert "metadata.password" not in facts
    assert "metadata.description" not in facts


def test_explicit_version_requires_matching_dataset_and_existing_identity(db: Database) -> None:
    """Reject cross-dataset and missing versions without silently falling back to latest."""
    dataset_id, before_id, _ = dataset_versions(db)
    other_dataset, _, _ = dataset_versions(db)
    with db.session() as session:
        with pytest.raises(NotFoundError, match="version"):
            extract_facts(session, other_dataset, before_id)
        with pytest.raises(NotFoundError, match="version"):
            extract_facts(session, dataset_id, "missing")
        with pytest.raises(NotFoundError, match="Dataset"):
            extract_facts(session, "missing", before_id)
