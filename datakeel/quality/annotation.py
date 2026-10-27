# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Overlay measured annotation agreement on the five-dimensional quality score."""

from datakeel.core.annotation_sampling import AnnotationQualityOverview, AnnotationQualityReport
from datakeel.core.models import JsonDocument
from datakeel.quality.models import DimensionView, IssueView, QualityView

MAX_SCORE = 100


def _agreement_components(report: AnnotationQualityReport) -> list[float]:
    result = report.result
    values = [
        pair.cohen_kappa.observed_agreement
        for pair in result.classification.pairs
        if pair.cohen_kappa.observed_agreement is not None
    ]
    values.extend(
        pair.match_rate * (pair.category_agreement or 0)
        for pair in result.boxes
        if pair.match_rate is not None
    )
    values.extend(pair.exact_f1 for pair in result.spans if pair.exact_f1 is not None)
    return values


def _annotation_dimension(
    quality: QualityView, overview: AnnotationQualityOverview
) -> DimensionView | None:
    report = overview.latest
    if report is None or not report.sample_count:
        return None
    components = _agreement_components(report)
    coverage = min(report.sample_count / quality.file_count, 1) if quality.file_count else 0
    score = 100 * coverage * sum(components) / len(components) if components else 0
    inspection = next((item for item in overview.inspections if item.batch_id == report.id), None)
    details = JsonDocument.model_validate(
        {
            "batch_id": report.id,
            "version_id": report.version_id,
            "sample_count": report.sample_count,
            "coverage": coverage,
            "agreement_components": components,
            "suspected_findings": len(report.result.findings),
            "classification": report.result.classification.model_dump(mode="json"),
            "boxes": [pair.model_dump(mode="json") for pair in report.result.boxes],
            "spans": [pair.model_dump(mode="json") for pair in report.result.spans],
            "latest_inspection": inspection.model_dump(mode="json") if inspection else None,
            "rework": report.comparison.model_dump(mode="json") if report.comparison else None,
            "rule": (
                "100 * sample coverage * mean(raw classification agreement, "
                "box match rate * matched category agreement, exact span F1); "
                "undefined comparisons are omitted; no comparable ratings score zero. "
                "Rule findings are suspicions, not confirmed defects."
            ),
        }
    ).root
    return DimensionView(
        score=round(score, 2),
        weight=0,
        configured_weight=quality.config.weights["annotation"],
        included=True,
        details=details,
    )


def apply_annotation_quality(
    quality: QualityView, overview: AnnotationQualityOverview
) -> QualityView:
    """Use raw agreement rather than chance-corrected coefficients for bounded scoring."""
    annotation = _annotation_dimension(quality, overview)
    if annotation is None:
        return quality
    dimensions = {**quality.dimensions, "annotation": annotation}
    denominator = sum(quality.config.weights[key] for key in dimensions)
    dimensions = {
        key: value.model_copy(
            update={"weight": round(100 * quality.config.weights[key] / denominator, 6)}
        )
        for key, value in dimensions.items()
    }
    total = round(sum(value.score * value.weight / 100 for value in dimensions.values()), 2)
    thresholds = quality.config.thresholds
    grade = next(
        (name for name in ("excellent", "good", "fair") if total >= thresholds[name]), "poor"
    )
    issues = [issue for issue in quality.issues if issue.dimension != "annotation"]
    if annotation.score < MAX_SCORE:
        severity = (
            "critical"
            if annotation.score < thresholds["critical"]
            else "warning"
            if annotation.score < thresholds["warning"]
            else "info"
        )
        issues.append(
            IssueView(
                dimension="annotation",
                severity=severity,
                code="annotation_agreement",
                message=f"Measured annotation agreement and coverage: {annotation.score:.2f}/100.",
            )
        )
    return quality.model_copy(
        update={"dimensions": dimensions, "total": total, "grade": grade, "issues": issues}
    )
