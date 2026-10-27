# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Map recorded image and point-cloud signals into the existing five dimensions."""

from math import isfinite

from pydantic import Field, JsonValue

from datakeel.core.models import FileItem, JsonDocument, Record
from datakeel.quality.models import IssueView

_DEFAULT_MIN_DENSITY = 1.0


class MediaAssessment(Record):
    """Carry measured multipliers and concrete reasons without reading source bytes."""

    completeness: float = 1.0
    consistency: float = 1.0
    distribution: float = 1.0
    score: float = 100.0
    observations: dict[str, JsonValue] = Field(default_factory=dict)
    issues: list[IssueView] = Field(default_factory=list[IssueView])


def _number(value: JsonValue, default: float = 0.0) -> float:
    if isinstance(value, int | float) and not isinstance(value, bool) and isfinite(value):
        return float(value)
    return default


def _issue(file: FileItem, code: str, message: str, dimension: str) -> IssueView:
    return IssueView(
        code=code,
        dimension=dimension,
        severity="warning",
        message=f"{file.filename}: {message}",
    )


def image_assessment(file: FileItem) -> MediaAssessment:
    """Use the measured overall score and preserve individual failed-check reasons."""
    measured = JsonDocument.model_validate(file.metadata).root.get("image_quality")
    if not isinstance(measured, dict) or "overall_score" not in measured:
        return MediaAssessment()
    score = max(0, min(100, _number(measured.get("overall_score"), 100)))
    issues: list[IssueView] = []
    checks = measured.get("checks", {})
    if isinstance(checks, dict):
        for key, check in checks.items():
            if isinstance(check, dict) and check.get("failed") is True:
                issues.append(
                    _issue(file, f"image_{key}", str(check.get("reason", key)), "completeness")
                )
    return MediaAssessment(
        completeness=score / 100,
        score=score,
        observations={"image": measured},
        issues=issues,
    )


def pointcloud_assessment(file: FileItem) -> MediaAssessment:
    """Penalize recorded invalid points, isolated points, sparse coverage and unit hints."""
    metadata = JsonDocument.model_validate(file.metadata).root
    measured = metadata.get("pointcloud_probe")
    if not isinstance(measured, dict):
        return MediaAssessment()
    policy = metadata.get("pointcloud_probe_params")
    invalid = max(0, min(1, _number(measured.get("invalid_ratio"))))
    outliers = max(0, min(1, _number(measured.get("outlier_ratio"))))
    count = _number(measured.get("point_count"))
    suspected = measured.get("unit_suspected") is True
    completeness = (1 - invalid) if count else 0.0
    distribution = (1 - outliers) * _coverage(measured, policy) if count else 0.0
    consistency = 0.2 if suspected else 1.0
    issues = _pointcloud_issues(file, measured, policy)
    return MediaAssessment(
        completeness=completeness,
        consistency=consistency,
        distribution=distribution,
        score=100 * min(completeness, consistency, distribution),
        observations={
            "pointcloud": measured,
            "source_pointcloud": metadata.get("source_pointcloud_probe"),
            "processing": metadata.get("pointcloud_processing"),
            "policy": metadata.get("pointcloud_probe_params"),
        },
        issues=issues,
    )


def _min_density(policy: JsonValue) -> float:
    value = policy.get("min_density") if isinstance(policy, dict) else None
    return max(0.0, _number(value, _DEFAULT_MIN_DENSITY))


def _coverage(measured: dict[str, JsonValue], policy: JsonValue) -> float:
    """Scale sparse coverage by the policy minimum; suspect units make density incomparable."""
    minimum = _min_density(policy)
    if measured.get("unit_suspected") is True or minimum == 0:
        return 1.0
    return max(0.0, min(1.0, _number(measured.get("density")) / minimum))


def _pointcloud_issues(
    file: FileItem, measured: dict[str, JsonValue], policy: JsonValue
) -> list[IssueView]:
    issues: list[IssueView] = []
    for key, label, dimension in (
        ("invalid_ratio", "NaN/Inf point ratio", "completeness"),
        ("outlier_ratio", "estimated statistical outlier ratio", "distribution"),
    ):
        ratio = _number(measured.get(key))
        if ratio > 0:
            issues.append(_issue(file, f"pointcloud_{key}", f"{label}: {ratio:.2%}", dimension))
    if _coverage(measured, policy) < 1:
        density, minimum = _number(measured.get("density")), _min_density(policy)
        issues.append(
            _issue(
                file,
                "pointcloud_sparse",
                f"main-body density {density:.6g} points/unit³ below minimum {minimum:g}",
                "distribution",
            )
        )
    if measured.get("unit_suspected") is True:
        issues.append(
            _issue(file, "pointcloud_unit", _unit_reason(measured, policy), "consistency")
        )
    return issues


def _unit_reason(measured: dict[str, JsonValue], policy: JsonValue) -> str:
    reasons = {
        "extent_exceeds_expected_maximum_possible_millimeters": (
            "Coordinate extent exceeds the expected maximum; possible millimeter units"
        ),
        "batch_extent_ratio_possible_unit_mismatch": (
            "Coordinate extent differs from the batch reference by the configured scale ratio"
        ),
    }
    code = str(measured.get("unit_reason"))
    reason = reasons.get(code, code)
    if isinstance(policy, dict):
        reason += (
            f"; expected maximum={policy.get('expected_max_extent')}, "
            f"reference extent={policy.get('reference_extent')}, "
            f"scale ratio={policy.get('scale_ratio')}, tolerance={policy.get('scale_tolerance')}"
        )
    return reason


def assess_file(file: FileItem) -> MediaAssessment:
    """Return a neutral assessment when a modality has no recorded quality evidence."""
    if file.modality == "image":
        return image_assessment(file)
    if file.modality == "point-cloud":
        return pointcloud_assessment(file)
    return MediaAssessment()
