# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Verify measured annotation agreement enters quality without rewriting old schemas."""

import pytest

from datakeel.core.annotation_models import (
    AgreementValue,
    AnnotationQAResult,
    ClassificationAgreement,
    ClassificationPair,
)
from datakeel.core.annotation_sampling import (
    AnnotationQualityOverview,
    AnnotationQualityReport,
)
from datakeel.core.models import FileItem, utcnow
from datakeel.quality import build_report, score_quality
from datakeel.quality.annotation import apply_annotation_quality


def overview(agreement: float | None = 0.5, samples: int = 2) -> AnnotationQualityOverview:
    """Build a frozen two-rater report without calling any model provider."""
    coefficient = AgreementValue(value=0, observed_agreement=agreement, sample_count=samples)
    report = AnnotationQualityReport(
        id="batch",
        dataset_id="dataset",
        version_id="version",
        name="Review",
        batch_digest="digest",
        sample_count=samples,
        annotation_count=2 * samples,
        created_at=utcnow(),
        result=AnnotationQAResult(
            sample_count=samples,
            annotator_count=2,
            classification=ClassificationAgreement(
                pairs=(
                    ClassificationPair(annotator_a="A", annotator_b="B", cohen_kappa=coefficient),
                ),
                fleiss_kappa=coefficient,
                krippendorff_alpha=coefficient,
            ),
        ),
    )
    return AnnotationQualityOverview(
        dataset_id="dataset", version_id="version", latest=report, batches=(report,)
    )


def baseline() -> list[FileItem]:
    """Use two complete, unique generated files whose annotations are initially absent."""
    return [
        FileItem(
            id=str(i),
            path=f"{i}.txt",
            filename=f"{i}.txt",
            sha256=str(i) * 64,
            size=10,
            modality="text",
        )
        for i in range(2)
    ]


def test_annotation_overlay_reweights_five_dimensions_and_reports_measured_agreement() -> None:
    """Half agreement gives 50 annotation points and 87.5 weighted total."""
    quality = apply_annotation_quality(score_quality(baseline()), overview())
    assert quality.dimensions["annotation"].score == 50
    assert quality.dimensions["annotation"].weight == 25
    assert quality.total == 87.5
    assert quality.grade == "good"
    assert sum(item.weight for item in quality.dimensions.values()) == pytest.approx(100)
    assert quality.dimensions["annotation"].details["batch_id"] == "batch"
    assert not any(issue.code == "annotation_excluded" for issue in quality.issues)
    report = build_report({"name": "Fixture"}, quality)
    assert "87.5" in report.body


def test_annotation_overlay_preserves_legacy_without_report() -> None:
    """Datasets without annotation QA retain their existing exclusion behavior."""
    quality = score_quality(baseline())
    assert (
        apply_annotation_quality(
            quality, AnnotationQualityOverview(dataset_id="dataset", version_id=None)
        )
        == quality
    )


@pytest.mark.parametrize(
    ("agreement", "samples", "expected"), [(1.0, 1, 50), (1.0, 2, 100), (None, 2, 0)]
)
def test_annotation_overlay_coverage_and_missing_comparisons_are_not_perfect(
    agreement: float | None, samples: int, expected: int
) -> None:
    """Partial or incomparable annotation evidence cannot claim full quality."""
    quality = apply_annotation_quality(score_quality(baseline()), overview(agreement, samples))
    assert quality.dimensions["annotation"].score == expected


def test_annotation_overlay_empty_report_does_not_include_dimension() -> None:
    """An empty stored report cannot enable a score dimension."""
    quality = score_quality(baseline())
    assert apply_annotation_quality(quality, overview(1, 0)) == quality
