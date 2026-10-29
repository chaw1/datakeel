# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Current file queries consume exact-content observations while pinned manifests stay immutable."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

from datakeel.core.models import FileItem
from datakeel.ontology.models import ObjectSet
from datakeel.storage.database import DatasetRow, VersionRow
from datakeel.storage.media_observations import read_media_observations
from datakeel.storage.object_queries import evaluate

if TYPE_CHECKING:
    from datakeel.storage.database import Database


def _source() -> FileItem:
    return FileItem(
        id="source-image",
        path="generated.png",
        filename="generated.png",
        modality="image",
        size=16,
        sha256="a" * 64,
        metadata={"source_note": "generated"},
    )


def _measured(file: FileItem, score: float) -> FileItem:
    return file.model_copy(
        update={
            "metadata": {
                "image_quality": {"overall_score": score},
                "width": 128,
                "height": 64,
                "pointcloud_preview": {"artifact_id": "irrelevant-preview"},
                "pointcloud_processing": {"operator": "unrelated"},
                "unrelated": "excluded",
            }
        }
    )


def _dataset(db: Database, source: FileItem, observations: list[FileItem]) -> str:
    with db.session() as session, session.begin():
        dataset = DatasetRow(
            name="generated-media-observations", files=[source.model_dump(mode="json")]
        )
        session.add(dataset)
        session.flush()
        session.add(
            VersionRow(
                id="source-version",
                dataset_id=dataset.id,
                created_at=1,
                manifest=[source.model_dump(mode="json")],
            )
        )
        for index, item in enumerate(observations, start=2):
            session.add(
                VersionRow(
                    id=f"measured-{index}",
                    dataset_id=dataset.id,
                    created_at=index,
                    manifest=[item.model_dump(mode="json")],
                )
            )
        session.flush()
        return dataset.id


def test_default_query_uses_newest_same_byte_measurement_without_mutating_source(
    db: Database,
) -> None:
    """A current original-file view receives the newest allowed measurement metadata only."""
    source = _source()
    dataset_id = _dataset(db, source, [_measured(source, 80), _measured(source, 12)])
    value = evaluate(db, ObjectSet(dataset_id=dataset_id)).objects[0]
    metadata = value.properties["metadata"]
    assert isinstance(metadata, dict)
    assert metadata["image_quality"] == {"overall_score": 12}
    assert metadata["source_note"] == "generated"
    assert metadata["width"] == 128
    assert not {"pointcloud_preview", "pointcloud_processing", "unrelated"}.intersection(metadata)
    assert value.asset_ref.version == "source-version"
    with db.session() as session:
        original = session.get(VersionRow, "source-version")
        assert original is not None
        assert original.manifest == [source.model_dump(mode="json")]


def test_default_quality_filter_selects_measured_low_source(db: Database) -> None:
    """The unchanged low-quality cleanup query can select an original source by measured quality."""
    source = _source()
    dataset_id = _dataset(db, source, [_measured(source, 12)])
    value = evaluate(db, ObjectSet(dataset_id=dataset_id, quality_max=60)).objects
    assert [item.asset_ref.asset_id for item in value] == [source.id]
    assert value[0].properties["quality"] == 12


@pytest.mark.parametrize("mismatch", ["id", "hash", "empty_hash"])
def test_observation_cannot_cross_file_or_nonempty_content_identity(
    db: Database, mismatch: str
) -> None:
    """Repeated names or mismatched content hashes are insufficient to transfer a quality result."""
    source = _source()
    update = (
        {"id": "different"}
        if mismatch == "id"
        else {"sha256": "b" * 64 if mismatch == "hash" else ""}
    )
    measured = _measured(source.model_copy(update=update), 12)
    dataset_id = _dataset(db, source, [measured])
    metadata = evaluate(db, ObjectSet(dataset_id=dataset_id)).objects[0].properties["metadata"]
    assert isinstance(metadata, dict)
    assert "image_quality" not in metadata


def test_newer_other_content_does_not_mask_older_matching_observation(db: Database) -> None:
    """Latest is resolved per exact ID and byte hash, never ID alone."""
    source = _source()
    different = source.model_copy(update={"sha256": "b" * 64})
    dataset_id = _dataset(db, source, [_measured(source, 12), _measured(different, 90)])
    value = evaluate(db, ObjectSet(dataset_id=dataset_id, quality_max=60)).objects
    assert len(value) == 1
    assert value[0].properties["quality"] == 12


@pytest.mark.parametrize(
    "query_fields",
    [
        {"version_ids": ["source-version"]},
        {"created_before": datetime.fromtimestamp(1.5, UTC)},
        {
            "created_after": datetime.fromtimestamp(0.5, UTC),
            "created_before": datetime.fromtimestamp(1.5, UTC),
        },
    ],
)
def test_explicit_version_and_date_queries_keep_original_unmeasured_manifest(
    db: Database,
    query_fields: dict[str, object],
) -> None:
    """A bounded historical query cannot acquire a later measurement revision implicitly."""
    source = _source()
    dataset_id = _dataset(db, source, [_measured(source, 12)])
    query = ObjectSet.model_validate({"dataset_id": dataset_id, **query_fields})
    value = evaluate(db, query).objects[0]
    metadata = value.properties["metadata"]
    assert isinstance(metadata, dict)
    assert "image_quality" not in metadata


def test_legacy_image_metadata_without_overall_score_is_not_a_new_measurement(db: Database) -> None:
    """Legacy dimensions cannot silently change the current quality projection."""
    source = _source()
    legacy = source.model_copy(update={"metadata": {"image_quality": {"width": 16}}})
    dataset_id = _dataset(db, source, [legacy])
    with db.session() as session:
        assert read_media_observations(session, dataset_id).observed(source) == source
