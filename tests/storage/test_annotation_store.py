# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Version ownership, immutable reports and reproducible annotation sampling contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest

from datakeel.core.annotation_models import AnnotationBatch, AnnotationRecord, OutlierPolicy
from datakeel.core.annotation_sampling import AnnotationImportRequest, SamplingRequest
from datakeel.core.errors import ConflictError, NotFoundError, ValidationError
from datakeel.storage.annotation_sampling import create_sampling_plan, select_sample
from datakeel.storage.annotation_store import get_annotation_quality, import_annotations
from datakeel.storage.dataset_service import import_paths, list_versions

if TYPE_CHECKING:
    from pathlib import Path

    from datakeel.core.annotation_sampling import AnnotationQualityReport
    from datakeel.storage.database import Database


@dataclass(frozen=True)
class AnnotationFixture:
    """Provide isolated generated version-owned annotation test inputs."""

    dataset_id: str
    version_id: str
    batch: AnnotationBatch
    report: AnnotationQualityReport


@pytest.fixture
def annotations(db: Database, tmp_path: Path) -> AnnotationFixture:
    """Generate a real manifest and three complete annotator panels for forty units."""
    paths = [tmp_path / f"sample-{number}.txt" for number in range(40)]
    for path in paths:
        path.write_text("Generated annotation quality sample")
    dataset = import_paths(db, "Generated annotation data", paths)
    version = list_versions(db, dataset.id)[0]
    batch = AnnotationBatch(
        annotations=tuple(
            AnnotationRecord(sample_id=file.id, annotator_id=actor, labels=("x",))
            for file in version.manifest
            for actor in ("reviewer-a", "reviewer-b", "reviewer-c")
        )
    )
    report = import_annotations(
        db,
        dataset.id,
        AnnotationImportRequest(version_id=version.id, batch=batch, idempotency_key="initial"),
    )
    return AnnotationFixture(dataset.id, version.id, batch, report)


def test_annotation_import_preserves_metrics_and_exact_idempotency(
    db: Database, annotations: AnnotationFixture
) -> None:
    """A complete retry reuses the report, timestamp and batch identity."""
    result = import_annotations(
        db,
        annotations.dataset_id,
        AnnotationImportRequest(
            version_id=annotations.version_id, batch=annotations.batch, idempotency_key="initial"
        ),
    )
    assert result == annotations.report
    view = get_annotation_quality(db, annotations.dataset_id, annotations.version_id)
    assert view.latest == annotations.report
    assert len(view.batches) == 1
    assert view.latest.sample_count == 40
    assert view.latest.annotation_count == 120


def test_annotation_import_rejects_changed_retry_identity(
    db: Database, annotations: AnnotationFixture
) -> None:
    """A retry identity cannot silently replace an immutable input batch or its name."""
    with pytest.raises(ConflictError, match="different inputs"):
        import_annotations(
            db,
            annotations.dataset_id,
            AnnotationImportRequest(
                version_id=annotations.version_id,
                batch=annotations.batch,
                name="Changed",
                idempotency_key="initial",
            ),
        )


def test_outlier_policy_is_part_of_the_frozen_batch_digest(
    db: Database, annotations: AnnotationFixture
) -> None:
    """Changed outlier thresholds are a different batch and cannot reuse a retry identity."""
    relaxed = annotations.batch.model_copy(
        update={"outlier_policy": OutlierPolicy(modified_z=6, corroborated_z=8)}
    )
    request = AnnotationImportRequest(
        version_id=annotations.version_id, batch=relaxed, idempotency_key="initial"
    )
    with pytest.raises(ConflictError, match="different inputs"):
        import_annotations(db, annotations.dataset_id, request)
    report = import_annotations(
        db, annotations.dataset_id, request.model_copy(update={"idempotency_key": "relaxed"})
    )
    assert report.batch_digest != annotations.report.batch_digest
    with pytest.raises(ValueError, match="unchanged review policy"):
        import_annotations(
            db,
            annotations.dataset_id,
            request.model_copy(
                update={"idempotency_key": "relaxed-rework", "rework_of": annotations.report.id}
            ),
        )


@pytest.mark.parametrize("invalid_kind", ["missing-version", "unknown-sample", "empty-batch"])
def test_annotation_import_rejects_unowned_or_empty_inputs(
    db: Database, annotations: AnnotationFixture, invalid_kind: str
) -> None:
    """Every nonempty annotation unit must resolve in the exact selected version."""
    batch = annotations.batch
    if invalid_kind == "unknown-sample":
        batch = AnnotationBatch(
            annotations=(AnnotationRecord(sample_id="absent", annotator_id="r", labels=()),)
        )
    if invalid_kind == "empty-batch":
        batch = AnnotationBatch(annotations=())
    with pytest.raises(NotFoundError if invalid_kind == "missing-version" else ValidationError):
        import_annotations(
            db,
            annotations.dataset_id,
            AnnotationImportRequest(
                version_id="absent"
                if invalid_kind == "missing-version"
                else annotations.version_id,
                batch=batch,
                idempotency_key=invalid_kind,
            ),
        )


def test_annotation_import_rework_keeps_original_report_and_comparison(
    db: Database, annotations: AnnotationFixture
) -> None:
    """Importing a repair adds history instead of changing the original metric evidence."""
    result = import_annotations(
        db,
        annotations.dataset_id,
        AnnotationImportRequest(
            version_id=annotations.version_id,
            batch=annotations.batch,
            rework_of=annotations.report.id,
            idempotency_key="repair",
        ),
    )
    assert result.comparison is not None
    assert result.comparison.corrected_count == 0
    assert len(get_annotation_quality(db, annotations.dataset_id).batches) == 2


def test_sampling_plan_reuses_identity_and_has_seeded_order_independent_selection(
    db: Database, annotations: AnnotationFixture
) -> None:
    """Seeded identity ranking selects without replacement independently of input order."""
    request = SamplingRequest(batch_id=annotations.report.id, aql=2.5, seed=26)
    first = create_sampling_plan(db, annotations.dataset_id, request)
    assert create_sampling_plan(db, annotations.dataset_id, request) == first
    assert (first.code_letter, first.effective_code_letter, first.sample_size) == ("D", "C", 5)
    all_ids = tuple({item.sample_id for item in annotations.batch.annotations})
    assert select_sample(all_ids, 5, 26) == select_sample(tuple(reversed(all_ids)), 5, 26)
    assert select_sample(all_ids, 5, 26) != select_sample(all_ids, 5, 27)
    assert len(set(first.sample_ids)) == 5


def test_ratio_sampling_rounds_up_and_requires_meaningful_acceptance(
    db: Database, annotations: AnnotationFixture
) -> None:
    """Fixed fractions use ceiling and never make every possible inspected outcome acceptable."""
    request = SamplingRequest(
        batch_id=annotations.report.id, method="ratio", ratio=0.251, acceptance_number=1
    )
    plan = create_sampling_plan(db, annotations.dataset_id, request)
    assert plan.sample_size == 11
    assert plan.code_letter is None
    with pytest.raises(ValidationError, match="smaller"):
        create_sampling_plan(
            db, annotations.dataset_id, request.model_copy(update={"acceptance_number": 11})
        )


def test_annotation_version_cannot_be_read_through_another_dataset(
    db: Database, annotations: AnnotationFixture, tmp_path: Path
) -> None:
    """Opaque version and batch identifiers do not bypass dataset ownership."""
    path = tmp_path / "other.txt"
    path.write_text("Different generated dataset")
    other = import_paths(db, "Other", [path])
    with pytest.raises(NotFoundError, match="version"):
        get_annotation_quality(db, other.id, annotations.version_id)
    with pytest.raises(NotFoundError, match="batch"):
        create_sampling_plan(db, other.id, SamplingRequest(batch_id=annotations.report.id))
