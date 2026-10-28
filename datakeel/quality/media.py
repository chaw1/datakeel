# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Map recorded image and point-cloud signals into the existing five dimensions."""

from math import isfinite

from pydantic import Field, JsonValue

from datakeel.core.models import FileItem, JsonDocument, Record
from datakeel.quality.models import IssueView

# Same value as the probe policy default; used only for probes recorded without a policy.
DEFAULT_MAX_OUTLIER_RATIO = 0.0004


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
    """Use the measured overall score and preserve individual failed-check reasons.

    An image that an operator could not decode scores zero completeness with
    its reason.
    """
    metadata = JsonDocument.model_validate(file.metadata).root
    failure = metadata.get("image_error")
    if isinstance(failure, dict):
        return _unreadable(file, failure, "image")
    measured = metadata.get("image_quality")
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
    """Penalize invalid rows, outliers beyond the file-level limit and sparse known captures.

    A file that an operator could not read scores zero completeness with its
    reason. Unit suspicion lowers consistency only; sparse coverage is not
    judged on a cloud whose unit is in doubt, and hints never change a score.
    """
    metadata = JsonDocument.model_validate(file.metadata).root
    failure = metadata.get("pointcloud_error")
    if isinstance(failure, dict):
        return _unreadable(file, failure, "pointcloud")
    measured = metadata.get("pointcloud_probe")
    if not isinstance(measured, dict):
        return MediaAssessment()
    policy = metadata.get("pointcloud_probe_params")
    rules = policy if isinstance(policy, dict) else {}
    invalid = max(0, min(1, _number(measured.get("invalid_ratio"))))
    count = _number(measured.get("point_count"))
    outliers, outlier_issue = _outliers(file, measured, rules)
    coverage, sparse_issue = _sparse(file, measured)
    completeness = (1 - invalid) if count else 0.0
    distribution = (1 - outliers) * coverage if count else 0.0
    consistency = 0.2 if measured.get("unit_suspected") is True else 1.0
    issues = [
        issue
        for issue in (
            _empty(file, count),
            _invalid(file, invalid),
            outlier_issue,
            sparse_issue,
            *_units(file, measured, rules),
        )
        if issue is not None
    ]
    return MediaAssessment(
        completeness=completeness,
        consistency=consistency,
        distribution=distribution,
        score=100 * min(completeness, consistency, distribution),
        observations={
            "pointcloud": measured,
            "source_pointcloud": metadata.get("source_pointcloud_probe"),
            "processing": metadata.get("pointcloud_processing"),
            "policy": policy,
        },
        issues=issues,
    )


def _unreadable(file: FileItem, failure: dict[str, JsonValue], modality: str) -> MediaAssessment:
    reason = f"{failure.get('operator')} could not process the file: {failure.get('reason')}"
    issue = _issue(file, f"{modality}_unreadable", reason, "completeness")
    return MediaAssessment(
        completeness=0.0,
        score=0.0,
        observations={f"{modality}_error": failure},
        issues=[issue.model_copy(update={"severity": "error"})],
    )


def _empty(file: FileItem, count: float) -> IssueView | None:
    """Explain the zero score of a readable cloud that declares no points."""
    if count > 0:
        return None
    return _issue(file, "pointcloud_empty", "the file contains no points", "completeness")


def _invalid(file: FileItem, ratio: float) -> IssueView | None:
    if ratio <= 0:
        return None
    return _issue(
        file, "pointcloud_invalid_ratio", f"NaN/Inf point ratio: {ratio:.2%}", "completeness"
    )


def _outliers(
    file: FileItem, measured: dict[str, JsonValue], rules: dict[str, JsonValue]
) -> tuple[float, IssueView | None]:
    """Report outliers only when the lower confidence bound exceeds the file-level limit."""
    ratio = max(0, min(1, _number(measured.get("outlier_ratio"))))
    low = max(0, min(1, _number(measured.get("outlier_ci_low"), ratio)))
    limit = _number(rules.get("max_outlier_ratio"), DEFAULT_MAX_OUTLIER_RATIO)
    if low <= limit:
        return 0.0, None
    high = _number(measured.get("outlier_ci_high"), ratio)
    sample = int(_number(measured.get("outlier_sample_count")))
    scope = (
        f"95% interval {low:.3%}-{high:.3%} from {sample} sampled points"
        if (measured.get("outlier_sampled") is True)
        else f"all {sample} finite points"
    )
    message = (
        f"outlier ratio {ratio:.3%} ({scope}; "
        f"{int(_number(measured.get('isolated_count')))} isolated, "
        f"{int(_number(measured.get('clustered_count')))} in separated clusters) "
        f"exceeds the limit {limit:.3%}"
    )
    return ratio, _issue(file, "pointcloud_outlier_ratio", message, "distribution")


def _sparse(file: FileItem, measured: dict[str, JsonValue]) -> tuple[float, IssueView | None]:
    """Compare nearest-neighbor spacing relative to the extent with the sensor-form limit.

    Spacing relative to the extent does not depend on the unit, so a small
    part in millimeters is judged like the same part in meters. A doubtful
    unit skips the check, and an undeclared sensor form only yields a hint.
    """
    relative = _number(measured.get("relative_spacing"))
    limit = _number(measured.get("spacing_limit"))
    if measured.get("unit_suspected") is True or limit <= 0 or relative <= limit:
        return 1.0, None
    message = (
        f"nearest-neighbor spacing is {relative:.4f} of the main-body extent, "
        f"above the {measured.get('sensor', 'unknown')} limit {limit:g}"
    )
    if measured.get("sparse_penalized") is not True:
        hint = _issue(file, "pointcloud_sparse_hint", message, "distribution")
        return 1.0, hint.model_copy(update={"severity": "info"})
    return limit / relative, _issue(file, "pointcloud_sparse", message, "distribution")


def _units(
    file: FileItem, measured: dict[str, JsonValue], rules: dict[str, JsonValue]
) -> list[IssueView]:
    extent = _number(measured.get("body_extent"))
    evidence = (
        f"main-body extent {extent:.6g} source units; sensor={measured.get('sensor', 'unknown')}, "
        f"expected maximum={rules.get('expected_max_extent')}, "
        f"reference extent={rules.get('reference_extent')}, scale ratio={rules.get('scale_ratio')}"
    )
    issues: list[IssueView] = []
    if measured.get("unit_suspected") is True:
        issues.append(
            _issue(
                file,
                "pointcloud_unit",
                f"unit in doubt, extent exceeds any single capture of this form "
                f"(millimeters read as meters?); {evidence}",
                "consistency",
            )
        )
    if measured.get("unit_hint") is not None:
        hint = _issue(
            file,
            "pointcloud_unit_hint",
            f"extent differs from the batch by about the scale ratio; mixed-scale batches "
            f"are legitimate, so this is only a hint; {evidence}",
            "consistency",
        )
        issues.append(hint.model_copy(update={"severity": "info"}))
    return issues


def assess_file(file: FileItem) -> MediaAssessment:
    """Return a neutral assessment when a modality has no recorded quality evidence."""
    if file.modality == "image":
        return image_assessment(file)
    if file.modality == "point-cloud":
        return pointcloud_assessment(file)
    return MediaAssessment()
