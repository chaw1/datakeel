# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Deterministic five-dimension quality scoring over a manifest snapshot."""

from collections import Counter, defaultdict
from copy import deepcopy
from math import isfinite, log
from pathlib import PurePosixPath
from typing import Any, cast

from datakeel.core.errors import ValidationError
from datakeel.core.models import FileItem
from datakeel.quality.image_pointcloud import apply_image_pointcloud
from datakeel.quality.media import apply_media, summarize_media
from datakeel.quality.models import QualityConfig, QualityView
from datakeel.quality.tabular import assess_tables, table_issues

MAX_SCORE = 100

DEFAULT_CONFIG: dict[str, Any] = {
    "weights": {
        "completeness": 25,
        "consistency": 20,
        "uniqueness": 15,
        "annotation": 25,
        "distribution": 15,
    },
    "thresholds": {"excellent": 90, "good": 75, "fair": 60, "critical": 40, "warning": 75},
    "exclude_annotation_when_absent": True,
    "distribution_field": "modality",
    "min_size_bytes": 1,
    "min_image_width": 1,
    "min_image_height": 1,
    "allowed_formats": {},
}


def quality_config(config: dict[str, Any] | QualityConfig | None = None) -> QualityConfig:
    """Merge a dataset override without changing the shared defaults."""
    if isinstance(config, QualityConfig):
        config = config.model_dump()
    result = deepcopy(DEFAULT_CONFIG)
    for key, value in (config or {}).items():
        if key not in result:
            msg = f"Unknown quality option: {key}"
            raise ValidationError(msg)
        if key in {"weights", "thresholds", "allowed_formats"}:
            if not isinstance(value, dict):
                msg = f"{key} must be an object"
                raise ValidationError(msg)
            result[key].update(value)
        else:
            result[key] = value
    _validate_numbers(result)
    _validate_options(result)
    return QualityConfig.model_validate(result)


def shannon_evenness(counts: list[int]) -> float:
    """H / log(k) on observed categories; one nonempty category is even by convention."""
    positive = [count for count in counts if count > 0]
    if not positive:
        return 0.0
    if len(positive) == 1:
        return 1.0
    total = sum(positive)
    return -sum((count / total) * log(count / total) for count in positive) / log(len(positive))


def _annotated(file: FileItem) -> bool:
    return any(
        file.metadata.get(key) not in (None, "", [], {})
        for key in ("annotation", "annotations", "label")
    )


def _complete(file: FileItem, config: QualityConfig) -> bool:
    if (
        file.size < config["min_size_bytes"]
        or file.metadata.get("empty")
        or file.metadata.get("corrupt")
    ):
        return False
    if file.modality == "image":
        image = file.metadata.get("image_quality", file.metadata)
        if not isinstance(image, dict):
            return False
        image = cast("dict[str, Any]", image)
        for dimension in ("width", "height"):
            observed = image.get(dimension)
            minimum = config[f"min_image_{dimension}"]
            if observed is None:
                if minimum > 1:
                    return False
            elif (
                not isinstance(observed, int | float)
                or not isfinite(observed)
                or observed < minimum
            ):
                return False
    return True


def score_quality(
    files: list[FileItem], config: dict[str, Any] | QualityConfig | None = None
) -> QualityView:
    """Score recorded evidence only: no file reads, remote calls, or manifest mutation."""
    resolved = quality_config(config)
    count = len(files)
    complete = sum(_complete(file, resolved) for file in files)
    annotations = sum(_annotated(file) for file in files)
    known_hashes = [file.sha256 for file in files if file.sha256]
    unique = len(set(known_hashes))
    groups: dict[str, Counter[str]] = defaultdict(Counter)
    for file in files:
        format_name = str(
            file.metadata.get("format") or PurePosixPath(file.filename).suffix.lstrip(".")
        ).lower()
        groups[file.modality][format_name or "unknown"] += 1
    consistent = _consistent(groups, resolved)
    labels, distribution_coverage = _distribution(files, resolved["distribution_field"])
    observed_labels = _observed(labels)
    raw = {
        "completeness": 100 * complete / count if count else 0,
        "consistency": 100 * consistent / count if count else 0,
        "uniqueness": 100 * unique / count if count else 0,
        "annotation": 100 * annotations / count if count else 0,
        "distribution": 100
        * shannon_evenness(list(observed_labels.values()))
        * distribution_coverage,
    }
    details = _evidence(files, resolved, complete, annotations, known_hashes, groups)
    tabular = assess_tables(files)
    for dimension, measured in tabular.scores.items():
        raw[dimension] = min(raw[dimension], measured)
        if tabular.files:
            details[dimension]["tabular_score"] = measured
            details[dimension]["tabular_rule"] = (
                "fraction of source rows affected by recorded rules"
            )
    visual = apply_image_pointcloud(files, raw, details)
    media = summarize_media(files)
    if media is not None:
        complete_ids = {file.id for file in files if _complete(file, resolved)}
        apply_media(media, files, complete_ids, raw, details)
    result = _summarize(raw, details, resolved, annotations, count)
    return result.model_copy(
        update={
            "tabular": tabular if tabular.files else None,
            "media": media,
            "issues": [*result.issues, *table_issues(tabular), *visual],
        }
    )


def _validate_numbers(result: dict[str, Any]) -> None:
    for key in ("weights", "thresholds"):
        if set(result[key]) != set(DEFAULT_CONFIG[key]):
            msg = f"Unknown {key} entry"
            raise ValidationError(msg)
        for value in result[key].values():
            if (
                isinstance(value, bool)
                or not isinstance(value, int | float)
                or not isfinite(value)
                or value < 0
            ):
                msg = f"{key} values must be finite nonnegative numbers"
                raise ValidationError(msg)
    t = result["thresholds"]
    if not 0 <= t["fair"] <= t["good"] <= t["excellent"] <= MAX_SCORE:
        msg = "Grade thresholds must satisfy 0 <= fair <= good <= excellent <= 100"
        raise ValidationError(msg)
    if not 0 <= t["critical"] <= t["warning"] <= MAX_SCORE:
        msg = "Issue thresholds must satisfy 0 <= critical <= warning <= 100"
        raise ValidationError(msg)


def _validate_options(result: dict[str, Any]) -> None:
    for key in ("min_size_bytes", "min_image_width", "min_image_height"):
        if isinstance(result[key], bool) or not isinstance(result[key], int) or result[key] < 0:
            msg = f"{key} must be a nonnegative integer"
            raise ValidationError(msg)
    if not isinstance(result["exclude_annotation_when_absent"], bool):
        msg = "exclude_annotation_when_absent must be boolean"
        raise ValidationError(msg)
    if not isinstance(result["distribution_field"], str) or not result["distribution_field"]:
        msg = "distribution_field must be a nonempty string"
        raise ValidationError(msg)
    for formats in result["allowed_formats"].values():
        if (
            not isinstance(formats, list)
            or not formats
            or not all(isinstance(x, str) for x in cast("list[Any]", formats))
        ):
            msg = "allowed_formats must map modalities to nonempty lists of formats"
            raise ValidationError(msg)


def _evidence(
    files: list[FileItem],
    config: QualityConfig,
    complete: int,
    annotations: int,
    hashes: list[str],
    groups: dict[str, Counter[str]],
) -> dict[str, Any]:
    count = len(files)
    consistent = _consistent(groups, config)
    field = config["distribution_field"]
    labels, distribution_coverage = _distribution(files, field)
    unique = len(set(hashes))
    return {
        "completeness": {
            "passed": complete,
            "total": count,
            "rule": "nonempty, readable and configured minimum size/resolution",
        },
        "consistency": {
            "passed": consistent,
            "total": count,
            "groups": {key: dict(value) for key, value in groups.items()},
            "rule": "dominant format within each modality, or configured allowed formats",
        },
        "uniqueness": {
            "unique_hashes": unique,
            "hashes_observed": len(hashes),
            "total": count,
            "rule": (
                "unique recorded content hashes / total files; missing hashes receive no credit"
            ),
        },
        "annotation": {
            "annotated": annotations,
            "total": count,
            "rule": "nonempty annotation, annotations or label metadata",
        },
        "distribution": {
            "field": field,
            "counts": dict(labels),
            "coverage": distribution_coverage,
            "rule": (
                "Shannon H / ln(observed categories), multiplied by nonmissing coverage; "
                "one observed category has evenness 1"
            ),
        },
    }


def _issues(
    dimensions: dict[str, Any], thresholds: dict[str, Any], count: int, *, excluded: bool
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for key in dimensions:
        score = dimensions[key]["score"]
        if key == "annotation" and excluded:
            issues.append(
                {
                    "dimension": key,
                    "severity": "info",
                    "code": "annotation_excluded",
                    "message": (
                        "No annotation evidence; this dimension is excluded "
                        "and remaining weights are normalized."
                    ),
                }
            )
        elif score < MAX_SCORE:
            severity = (
                "critical"
                if score < thresholds["critical"]
                else "warning"
                if score < thresholds["warning"]
                else "info"
            )
            issues.append(
                {
                    "dimension": key,
                    "severity": severity,
                    "code": f"{key}_below_target",
                    "message": (
                        f"{key}: {score:.2f}/100; "
                        "inspect the dimension details for measured evidence."
                    ),
                }
            )
    if not count:
        issues.append(
            {
                "dimension": "completeness",
                "severity": "critical",
                "code": "empty_dataset",
                "message": "The dataset has no files.",
            }
        )
    return issues


def _consistent(groups: dict[str, Counter[str]], config: QualityConfig) -> int:
    consistent = 0
    for modality, formats in groups.items():
        allowed = config["allowed_formats"].get(modality)
        if allowed is not None:
            consistent += sum(size for name, size in formats.items() if name in allowed)
        else:
            consistent += max(formats.values())
    return consistent


def _observed(labels: Counter[str]) -> dict[str, int]:
    return {
        key: value
        for key, value in labels.items()
        if key not in {"[missing]", "unknown", "None", ""}
    }


def _distribution(files: list[FileItem], field: str) -> tuple[Counter[str], float]:
    labels = Counter(
        str(file.modality if field == "modality" else file.metadata.get(field, "[missing]"))
        for file in files
    )
    coverage = sum(_observed(labels).values()) / len(files) if files else 0
    return labels, coverage


def _summarize(
    raw: dict[str, float],
    details: dict[str, Any],
    resolved: QualityConfig,
    annotations: int,
    count: int,
) -> QualityView:
    excluded = annotations == 0 and resolved["exclude_annotation_when_absent"]
    weights = {
        key: float(value) if key != "annotation" or not excluded else 0
        for key, value in resolved["weights"].items()
    }
    denominator = sum(weights.values())
    if denominator == 0:
        msg = "At least one included quality dimension must have positive weight"
        raise ValidationError(msg)
    dimensions = {
        key: {
            "score": round(score, 2),
            "weight": round(100 * weights[key] / denominator, 6),
            "configured_weight": resolved["weights"][key],
            "included": not (key == "annotation" and excluded),
            "details": details[key],
        }
        for key, score in raw.items()
    }
    total = round(sum(raw[key] * weights[key] / denominator for key in raw), 2)
    thresholds = resolved["thresholds"]
    grade = next(
        (name for name in ("excellent", "good", "fair") if total >= thresholds[name]), "poor"
    )
    issues = _issues(dimensions, thresholds, count, excluded=excluded)
    return QualityView.model_validate(
        {
            "dimensions": dimensions,
            "total": total,
            "grade": grade,
            "issues": issues,
            "file_count": count,
            "config": resolved,
        }
    )
