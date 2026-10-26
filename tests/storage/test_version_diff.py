# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Version comparisons remain complete, scoped, portable, and bounded at 10,000 files."""

import gc
import tracemalloc
from pathlib import Path

import pytest
from sqlalchemy import select

from datakeel.core.errors import ConflictError, NotFoundError, ValidationError
from datakeel.core.models import FileItem
from datakeel.storage.database import Database, DatasetRow, EventRow, VersionRow
from datakeel.storage.dataset_service import import_paths
from datakeel.storage.evidence_rows import AssertionRow
from datakeel.storage.version_diff import compare_versions


def _versions(db: Database, tmp_path: Path) -> tuple[str, str, str]:
    path = tmp_path / "example.txt"
    path.write_text("Generated comparison sample.", encoding="utf-8")
    dataset = import_paths(db, "comparison-example", [path])
    with db.session() as session:
        original = session.scalar(select(VersionRow).where(VersionRow.dataset_id == dataset.id))
        assert original is not None
        template = FileItem.model_validate(original.manifest[0])
        before = [template.model_copy(update={"id": str(i)}) for i in range(4)]
        after = [
            before[0],
            before[1].model_copy(update={"sha256": "f" * 64}),
            before[2].model_copy(
                update={
                    "metadata": {"annotations": [{"label": "example"}], "labels": ["one", "two"]}
                }
            ),
            template.model_copy(update={"id": "4", "size": 0}),
        ]
        original.manifest = [item.model_dump(mode="json") for item in before]
        other = VersionRow(
            dataset_id=dataset.id, manifest=[item.model_dump(mode="json") for item in after]
        )
        session.add(other)
        session.flush()
        session.add(EventRow(event_id="example-event", idempotency_key="example-event", payload={}))
        session.flush()
        session.add(
            AssertionRow(
                id="assertion",
                subject_id="2",
                predicate="has_label",
                producer_event_id="example-event",
                status="accepted",
                payload={"subject": {"version": other.id}},
            )
        )
        session.commit()
        return dataset.id, original.id, other.id


def test_diff_five_categories_and_annotation_quality_evidence_changes(
    db: Database, tmp_path: Path
) -> None:
    """Classify hash changes before metadata changes and count complete version measurements."""
    dataset, before, after = _versions(db, tmp_path)
    result = compare_versions(db, dataset, before, after)
    assert result.counts.model_dump() == {
        "added": 1,
        "removed": 1,
        "content_changed": 1,
        "metadata_changed": 1,
        "unchanged": 1,
    }
    assert result.before_summary.annotation_count == 0
    assert result.after_summary.annotation_count == 1
    assert result.after_summary.label_count == 2
    assert result.before_summary.quality_score > result.after_summary.quality_score
    assert result.after_summary.evidence_decisions == {"accepted": 1}
    assert "object_key" not in result.model_dump_json()
    assert str(tmp_path) not in result.model_dump_json()


def test_diff_filter_and_pagination_keep_global_counts(db: Database, tmp_path: Path) -> None:
    """Page sorted stable file identities and retain global counts under category filtering."""
    dataset, before, after = _versions(db, tmp_path)
    first = compare_versions(db, dataset, before, after, (0, 2))
    second = compare_versions(db, dataset, before, after, (2, 2))
    assert [item.file_id for item in first.files] == ["0", "1"]
    assert [item.file_id for item in second.files] == ["2", "3"]
    assert first.next_offset == 2
    final = compare_versions(db, dataset, before, after, (4, 2))
    assert final.next_offset is None
    filtered = compare_versions(db, dataset, before, after, (0, 1), "metadata_changed")
    assert [item.file_id for item in filtered.files] == ["2"]
    assert filtered.counts == first.counts
    assert filtered.next_offset is None


def test_diff_rejects_cross_dataset_and_invalid_page(db: Database, tmp_path: Path) -> None:
    """Never compare a version from another dataset or accept unbounded response requests."""
    dataset, before, after = _versions(db, tmp_path)
    with pytest.raises(NotFoundError):
        compare_versions(db, "another-dataset", before, after)
    with pytest.raises(ValidationError):
        compare_versions(db, dataset, before, after, (0, 1001))


def test_diff_duplicate_identity_rejected(db: Database, tmp_path: Path) -> None:
    """Invalid legacy manifests cannot silently hide duplicated file identities."""
    dataset, before, after = _versions(db, tmp_path)
    with db.session() as session:
        row = session.get(VersionRow, before)
        assert row is not None
        row.manifest = [row.manifest[0], row.manifest[0]]
        session.commit()
    with pytest.raises(ConflictError, match="duplicate"):
        compare_versions(db, dataset, before, after)


def test_diff_ten_thousand_files_page_has_bounded_python_memory(db: Database) -> None:
    """JSON manifests expand in the database; Python retains only cursors and the output page."""
    with db.session() as session:
        dataset = DatasetRow(name="generated-scale", files=[])
        session.add(dataset)
        session.flush()
        manifest = [
            FileItem(
                id=f"file-{i:05}",
                path="private",
                filename=f"sample-{i}.txt",
                sha256=f"{i:064x}",
                size=20,
                modality="text",
            ).model_dump(mode="json")
            for i in range(10000)
        ]
        before = VersionRow(dataset_id=dataset.id, manifest=manifest)
        after = VersionRow(dataset_id=dataset.id, manifest=manifest)
        session.add_all([before, after])
        session.commit()
        dataset_id, before_id, after_id = dataset.id, before.id, after.id
    del manifest
    gc.collect()
    tracemalloc.start()
    try:
        result = compare_versions(db, dataset_id, before_id, after_id, (9900, 50))
        _current, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert result.counts.unchanged == 10000
    assert len(result.files) == 50
    assert result.next_offset == 9950
    assert peak < 8 * 1024 * 1024


@pytest.mark.parametrize(("before_value", "after_value"), [(1, True), ("first", "second")])
def test_diff_metadata_classification_keeps_json_types_and_private_changes(
    db: Database, tmp_path: Path, *, before_value: int | str, after_value: bool | str
) -> None:
    """Compare all semantic metadata while excluding physical location from public output."""
    dataset, before, after = _versions(db, tmp_path)
    with db.session() as session:
        left, right = session.get(VersionRow, before), session.get(VersionRow, after)
        assert left is not None
        assert right is not None
        base = FileItem.model_validate(left.manifest[0])
        left.manifest = [
            base.model_copy(update={"metadata": {"token": before_value}}).model_dump(mode="json")
        ]
        right.manifest = [
            base.model_copy(update={"metadata": {"token": after_value}}).model_dump(mode="json")
        ]
        session.commit()
    result = compare_versions(db, dataset, before, after)
    assert result.counts.metadata_changed == 1
    assert result.files[0].before is not None
    assert result.files[0].before.metadata == {}
