# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Fail-closed reference selection and typed set boundaries using generated local inputs."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from datakeel.core.evidence_models import Assertion, TextSpan
from datakeel.core.models import AssetRef
from datakeel.core.vector_models import VectorError
from datakeel.dataset_store.rows import VersionRow
from datakeel.evidence.vector_set_execution import compute_set
from datakeel.storage.database import Database
from datakeel.storage.evidence_import import source_manifest
from datakeel.storage.evidence_projection import evidence_watermark
from datakeel.storage.evidence_store import list_assertions
from datakeel.storage.vector_current import vector_assertion_current
from datakeel.storage.vector_references import reference_file
from tests.evidence.test_vector_set_execution import set_pipeline
from tests.evidence.vector_helpers import vector_dataset, vector_prepare, vector_run


@pytest.mark.parametrize("reference", [{"object_type": "dataset"}, {"include_deleted": True}])
def test_reference_requires_live_file_selection(
    db: Database, tmp_path: Path, reference: dict[str, object]
) -> None:
    """Reference queries cannot silently turn administrative/deleted resources into R."""
    target = vector_dataset(db, tmp_path / "target")
    with pytest.raises(VectorError, match="live_files"):
        vector_prepare(db, target, set_pipeline("evidence.coverage_gap", {"reference": reference}))


def test_reference_full_size_limit_refuses_before_slicing(db: Database, tmp_path: Path) -> None:
    """Even a display limit of one cannot hide excess reference members at prepare."""
    target = vector_dataset(db, tmp_path / "target", (b"t",))
    reference = vector_dataset(db, tmp_path / "ref", (b"a", b"b"))
    with pytest.raises(VectorError, match="capacity"):
        vector_prepare(
            db,
            target,
            set_pipeline(
                "evidence.coverage_gap",
                {"reference": {"dataset_id": reference, "limit": 1}, "max_samples": 1},
            ),
        )


def test_reference_multiple_versions_of_one_asset_refused(db: Database, tmp_path: Path) -> None:
    """A complete ObjectSet with ambiguous same-ID versions cannot overwrite a frozen payload."""
    target = vector_dataset(db, tmp_path / "target", (b"t",))
    reference = vector_dataset(db, tmp_path / "ref", (b"a",))
    original, files = source_manifest(db, reference)
    with db.session() as session:
        row = VersionRow(dataset_id=reference, manifest=[f.model_dump(mode="json") for f in files])
        session.add(row)
        session.commit()
        latest = row.id
    with pytest.raises(VectorError, match="ambiguous_version"):
        vector_prepare(
            db,
            target,
            set_pipeline(
                "evidence.coverage_gap",
                {"reference": {"dataset_id": reference, "version_ids": [original, latest]}},
            ),
        )


def test_missing_reference_and_scope_return_typed_errors(db: Database) -> None:
    """Missing immutable input versions and scope fail without constructing any transport."""
    with db.session() as session, pytest.raises(VectorError, match="unavailable"):
        reference_file(session, AssetRef(asset_type="file", asset_id="missing", version="missing"))
    node = set_pipeline("evidence.coverage_gap", {"reference": {}}).nodes[-1]
    with pytest.raises(VectorError, match="scope_missing"):
        compute_set(db, (), node, None)
    with db.session() as session:
        watermark = evidence_watermark(session)
    assert len(watermark.digest()) == 64


def test_gap_all_target_failures_retain_target_counts(db: Database, tmp_path: Path) -> None:
    """A valid R cannot make entirely failed T look like successful empty coverage."""
    target = vector_dataset(db, tmp_path / "target", (b"\xff",))
    reference = vector_dataset(db, tmp_path / "ref", (b"r",))
    task = vector_run(
        db, target, set_pipeline("evidence.coverage_gap", {"reference": {"dataset_id": reference}})
    )
    assert task.state == "FAILED"
    assert task.vector
    assert task.vector.reason == "vector_all_inputs_failed"
    assert task.vector.nodes[-1].counts.input == 1
    assert task.vector.nodes[-1].counts.failed == 1
    assert list_assertions(db) == []


def test_set_whole_anchor_and_missing_producer_refused(db: Database, tmp_path: Path) -> None:
    """Candidate boundaries require Whole anchors and retain only verifiable source events."""
    target = vector_dataset(db, tmp_path / "target", (b"same", b"same"))
    task = vector_run(
        db, target, set_pipeline("evidence.semantic_cluster", {"eps": 0.0, "min_samples": 2})
    )
    assert task.state == "COMPLETED"
    fact = list_assertions(db)[0]
    bad = fact.anchors[0].model_copy(update={"selector": TextSpan(start=0, end=1)})
    with pytest.raises(ValidationError, match="Invalid typed"):
        Assertion.model_validate({**fact.model_dump(), "anchors": (bad,)})
    reference = vector_dataset(db, tmp_path / "ref", (b"r",))
    task = vector_run(
        db,
        target,
        set_pipeline(
            "evidence.coverage_gap", {"reference": {"dataset_id": reference}, "threshold": 1.0}
        ),
    )
    assert task.state == "COMPLETED"
    gap = next(f for f in list_assertions(db) if f.predicate == "coverage_gap")
    with db.session() as session:
        assert not vector_assertion_current(
            session, gap.model_copy(update={"producer_event_id": "missing"})
        )
