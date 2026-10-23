# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for scoring."""

from __future__ import annotations

from copy import deepcopy
from math import log
from typing import TYPE_CHECKING

import pytest

from datakeel.core.models import FileItem
from datakeel.quality import DEFAULT_CONFIG, score_quality, shannon_evenness
from datakeel.quality.models import QualityConfig

if TYPE_CHECKING:
    from pydantic import JsonValue


def file(
    index: int, modality: str = "text", suffix: str = "txt", **metadata: JsonValue
) -> FileItem:
    """Provide the file test fixture."""
    return FileItem(
        id=str(index),
        path=f"objects/{index}",
        filename=f"{index}.{suffix}",
        sha256=str(index).zfill(64),
        size=20,
        modality=modality,
        metadata=metadata,
    )


def test_default_weights_five_dimensions_and_annotation_renormalization() -> None:
    """Verify default weights five dimensions and annotation renormalization."""
    files = [file(1), file(2, "image", "png")]
    result = score_quality(files)
    assert set(result["dimensions"]) == {
        "completeness",
        "consistency",
        "uniqueness",
        "annotation",
        "distribution",
    }
    assert result["total"] == 100
    assert result["grade"] == "excellent"
    assert result["dimensions"]["annotation"]["included"] is False
    assert result["dimensions"]["annotation"]["weight"] == 0
    assert sum(item["weight"] for item in result["dimensions"].values()) == pytest.approx(100)
    included = score_quality(files, {"exclude_annotation_when_absent": False})
    assert included["total"] == 75
    assert included["dimensions"]["annotation"]["included"] is True
    assert {key: item["weight"] for key, item in included["dimensions"].items()} == DEFAULT_CONFIG[
        "weights"
    ]


def test_completeness_threshold_recalculation_and_config_does_not_mutate() -> None:
    """Verify completeness threshold recalculation and config does not mutate."""
    files = [file(1, "image", "png", image_quality={"width": 128, "height": 128})]
    config = {"min_image_width": 256}
    original = deepcopy(config)
    baseline = score_quality(files)
    strict = score_quality(files, config)
    assert baseline["total"] > strict["total"]
    assert strict["dimensions"]["completeness"]["score"] == 0
    assert config == original
    assert DEFAULT_CONFIG["min_image_width"] == 1
    assert score_quality(files, {"min_size_bytes": 21})["dimensions"]["completeness"]["score"] == 0


def test_consistency_compares_formats_within_modality() -> None:
    """Verify consistency compares formats within modality."""
    files = [file(1), file(2, "image", "png"), file(3, "image", "jpg")]
    baseline = score_quality(files)
    assert baseline["dimensions"]["consistency"]["score"] == 66.67
    allowed = score_quality(files, {"allowed_formats": {"image": ["png", "jpg"]}})
    assert allowed["dimensions"]["consistency"]["score"] == 100
    assert (
        score_quality([file(1), file(2, "image", "png")])["dimensions"]["consistency"]["score"]
        == 100
    )


def test_duplicates_missing_hash_and_partial_annotation() -> None:
    """Verify duplicates missing hash and partial annotation."""
    files = [file(1, label=0), file(2), file(3)]
    files[1] = files[1].model_copy(update={"sha256": files[0].sha256})
    files[2] = files[2].model_copy(update={"sha256": ""})
    result = score_quality(files)
    assert result["dimensions"]["uniqueness"]["score"] == 33.33
    assert result["dimensions"]["annotation"]["score"] == 33.33
    assert result["dimensions"]["annotation"]["included"] is True
    assert any(issue["severity"] == "critical" for issue in result["issues"])


def test_shannon_distribution_with_custom_label() -> None:
    """Verify shannon distribution with custom label."""
    files = [file(i, label="a" if i < 9 else "b") for i in range(10)]
    result = score_quality(files, {"distribution_field": "label"})
    expected = -(0.9 * log(0.9) + 0.1 * log(0.1)) / log(2) * 100
    assert result["dimensions"]["distribution"]["score"] == round(expected, 2)
    assert shannon_evenness([1, 1]) == 1
    assert shannon_evenness([10]) == 1
    assert shannon_evenness([]) == 0


def test_severity_and_grade_thresholds_are_configurable() -> None:
    """Verify severity and grade thresholds are configurable."""
    files = [file(i) for i in range(4)]
    files[0].metadata["empty"] = True
    normal = score_quality(files)
    stricter = score_quality(
        files, {"thresholds": {"excellent": 99, "critical": 80, "warning": 90}}
    )
    assert normal["grade"] == "excellent"
    assert stricter["grade"] == "good"
    assert (
        next(issue for issue in normal["issues"] if issue["dimension"] == "completeness")[
            "severity"
        ]
        == "info"
    )
    assert (
        next(issue for issue in stricter["issues"] if issue["dimension"] == "completeness")[
            "severity"
        ]
        == "critical"
    )


def test_empty_dataset_is_not_healthy() -> None:
    """Verify empty dataset is not healthy."""
    result = score_quality([])
    assert result["total"] == 0
    assert result["grade"] == "poor"
    assert any(issue["code"] == "empty_dataset" for issue in result["issues"])


@pytest.mark.parametrize(
    "config",
    [
        {"weights": {"annotation": -1}},
        {"weights": {"completeness": float("nan")}},
        {"thresholds": {"good": 95}},
        {"weights": dict.fromkeys(DEFAULT_CONFIG["weights"], 0)},
        {"min_image_width": -1},
        {"exclude_annotation_when_absent": "false"},
        {"unexpected": 1},
        {"allowed_formats": {"text": "txt"}},
    ],
)
def test_invalid_configuration_rejected(config: dict[str, JsonValue]) -> None:
    """Verify invalid configuration rejected."""
    with pytest.raises(ValueError, match=r".+"):
        score_quality([file(1)], config)


def test_missing_distribution_values_receive_no_credit() -> None:
    """Verify missing distribution values receive no credit."""
    result = score_quality([file(1)], {"distribution_field": "category"})
    assert result["dimensions"]["distribution"]["score"] == 0
    assert result["dimensions"]["distribution"]["details"]["coverage"] == 0


def test_resolution_threshold_requires_measured_dimensions() -> None:
    """Verify resolution threshold requires measured dimensions."""
    result = score_quality([file(1, "image", "png")], {"min_image_width": 512})
    assert result["dimensions"]["completeness"]["score"] == 0


def test_malformed_image_measurement_is_an_issue_instead_of_an_exception() -> None:
    """Verify malformed image measurement is an issue instead of an exception."""
    result = score_quality([file(1, "image", "png", image_quality={"width": "invalid"})])
    assert result["dimensions"]["completeness"]["score"] == 0


def test_uniform_distribution_has_no_rounding_only_issue() -> None:
    """Verify uniform distribution has no rounding only issue."""
    files = [file(index, label=str(index % 3)) for index in range(9)]
    result = score_quality(files, {"distribution_field": "label"})
    assert result["dimensions"]["distribution"]["score"] == 100
    assert not any(issue["dimension"] == "distribution" for issue in result["issues"])


def test_typed_negative_weight_is_rejected_before_scoring() -> None:
    """Verify typed negative weight is rejected before scoring."""
    config = QualityConfig.model_validate(
        {**DEFAULT_CONFIG, "weights": {**DEFAULT_CONFIG["weights"], "completeness": -25}}
    )
    with pytest.raises(ValueError, match="finite nonnegative"):
        score_quality([file(1)], config)


def test_typed_nested_mutation_is_revalidated_before_scoring() -> None:
    """Verify typed nested mutation is revalidated before scoring."""
    config = QualityConfig.model_validate(DEFAULT_CONFIG)
    config.thresholds["good"] = 101
    with pytest.raises(ValueError, match="Grade thresholds"):
        score_quality([file(1)], config)
