# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Independent explicit geometry, metric formulas and floating-boundary assertion anchors."""

import math

import pytest
from pydantic import ValidationError

from scripts.we_e5.fixtures import explicit_case
from scripts.we_e5.metrics import clustering, quality, score
from scripts.we_e5.models import NumericInput, Point, Workload
from scripts.we_e5.numeric import decisions, f64_scores, faiss_scores, normalized
from scripts.we_e5.report import compare
from scripts.we_e5.worker import rss_bytes


def case_for(values: tuple[tuple[str, tuple[float, ...]], ...], **changes: object) -> NumericInput:
    """Use a complete handwritten coordinate case, never derive expected labels from FAISS."""
    values_dict = explicit_case().model_dump()
    values_dict.update(
        points=tuple(Point(asset_id=k, values=v) for k, v in values),
        targets=tuple(sorted(k for k, _ in values)),
        references=(),
        prefix=len(values[0][1]),
        duplicate_gold=None,
        cluster_gold=None,
        gap_gold=None,
    )
    values_dict.update(changes)
    return NumericInput.model_validate(values_dict)


def test_handwritten_oracle_checks_production_and_faiss_all_metrics() -> None:
    """Scaled axes independently prescribe pairs, survivors, noise, nearest ties and gold."""
    report = compare(explicit_case())
    for result in (report.f64, report.faiss):
        assert result.pairs == (("a", "b"), ("c", "d"))
        assert result.removed == ("b", "d")
        assert result.labels == (0, 0, 1, 1, -1)
        assert result.noise == ("z",)
        assert result.gaps == (("c", "a"), ("d", "a"), ("z", "a"))
        assert result.reduction == 2 / 5
    for metrics in (report.f64_quality, report.faiss_quality):
        assert metrics.removal != "not_available"
        assert metrics.removal.f1 == 1
        assert metrics.direct_pair != "not_available"
        assert metrics.direct_pair.f1 == 1
        assert metrics.survival == metrics.exactly_one == 1
        assert metrics.ari == metrics.nmi == 1
        assert metrics.noise != "not_available"
        assert metrics.noise.f1 == 1
        assert metrics.gap != "not_available"
        assert metrics.gap.f1 == 1
    assert report.decision_differences == ()


def test_both_index_and_queries_use_same_normalized_f32_prefix() -> None:
    """Check actual IP numbers on nonsymmetric scaled vectors; either unnormalized side fails."""
    case = case_for((("b", (3.0, 4.0, 100.0)), ("a", (8.0, 0.0, 99.0))), prefix=2)
    samples = normalized(case)
    assert samples[0].vector == (1.0, 0.0)
    assert samples[1].vector == pytest.approx((0.6, 0.8), abs=1e-7)
    faiss = faiss_scores(samples)
    exact = f64_scores(samples)
    assert faiss[0][0] == pytest.approx(1.0, abs=1e-7)
    assert faiss[1][1] == pytest.approx(1.0, abs=1e-7)
    assert faiss[0][1] == pytest.approx(0.6, abs=1e-7)
    assert faiss[1][0] == pytest.approx(0.6, abs=1e-7)
    assert exact[0][1] == pytest.approx(0.6, abs=1e-7)
    assert (
        compare(case).normalized_f32_hashes
        == compare(
            case.model_copy(update={"points": tuple(reversed(case.points))})
        ).normalized_f32_hashes
    )


@pytest.mark.parametrize(
    "vector", [(0.0, 0.0), (float("nan"), 1.0), (float("inf"), 1.0), (float("-inf"), 1.0)]
)
def test_invalid_nonfinite_or_zero_vectors_rejected(vector: tuple[float, ...]) -> None:
    """Neither branch may silently index or score an invalid vector."""
    reason = None
    try:
        compare(case_for((("a", vector),)))
    except ValueError as error:
        reason = str(error)
    assert reason in {"zero_vector_after_prefix", "nonfinite_f32"}


def test_zero_after_prefix_rejected_even_when_full_vector_nonzero() -> None:
    """Normalization is after the shared prefix, with an explicit zero-vector refusal."""
    with pytest.raises(ValueError, match="zero_vector_after_prefix"):
        compare(case_for((("a", (0.0, 2.0)),), prefix=1))


def test_greedy_seen_set_does_not_remove_transitive_chain() -> None:
    """B is removed by a; removed b cannot in turn remove c."""
    case = case_for(
        tuple(
            (key, (math.cos(angle), math.sin(angle)))
            for key, angle in (("a", 0.0), ("b", 0.4), ("c", 0.8))
        ),
        threshold=0.9,
    )
    report = compare(case)
    assert report.f64.pairs == report.faiss.pairs == (("a", "b"), ("b", "c"))
    assert report.f64.removed == report.faiss.removed == ("b",)


def test_greedy_exact_score_ties_choose_smallest_kept_asset_id() -> None:
    """A and b survive; c has equal similarity to both, so only asset ID resolves its parent."""
    case = case_for((("b", (0.0, 1.0)), ("c", (1.0, 1.0)), ("a", (1.0, 0.0))), threshold=0.7)
    report = compare(case)
    assert report.f64.representatives == report.faiss.representatives == (("c", "a"),)


def test_inclusive_threshold_and_dbscan_distance_strict_gap() -> None:
    """Orthogonal points lie exactly on duplicate=0, distance=1 and gap=0 boundaries."""
    case = case_for(
        (("a", (1.0, 0.0)), ("b", (0.0, 1.0))),
        threshold=0.0,
        eps=1.0,
        references=("a",),
        gap_threshold=0.0,
    )
    report = compare(case)
    assert report.f64.pairs == report.faiss.pairs == (("a", "b"),)
    assert report.f64.labels == report.faiss.labels == (0, 0)
    assert report.f64.gaps == report.faiss.gaps == ()


def test_float_error_and_threshold_disagreement_are_retained() -> None:
    """A real F32/F64 score gap can straddle a threshold; it must remain an explicit mismatch."""
    case = case_for((("a", (1.0, 0.0)), ("b", (1.0, 1.0))))
    samples = normalized(case)
    f64, faiss = f64_scores(samples)[0][1], faiss_scores(samples)[0][1]
    assert f64 != faiss
    report = compare(case.model_copy(update={"threshold": (f64 + faiss) / 2}))
    assert "pairs" in report.decision_differences
    assert report.float_error["different"] > 0
    assert report.float_error["max_absolute"] >= abs(f64 - faiss)


def test_absent_gold_metrics_are_not_available() -> None:
    """Matching two implementations does not manufacture any form of semantic gold."""
    case = case_for((("a", (1.0, 0.0)), ("b", (0.0, 1.0))))
    metrics = quality(case, compare(case).f64).model_dump()
    assert all(value == "not_available" for value in metrics.values())


def test_metric_formulas_include_chance_adjustment_and_arithmetic_nmi() -> None:
    """Hand-computed confusion counts distinguish ARI from raw pair agreement."""
    ari, nmi = clustering((0, 0, 1, 1), (0, 1, 0, 1))
    assert ari == pytest.approx(-0.5)
    assert nmi == 0
    assert clustering((0, 0, 1, 1), (3, 3, 2, 2)) == (1, 1)
    assert clustering((-1, -1), (-1, -1)) == (1, 1)
    assert score({"a", "b"}, {"a", "c", "d"}).model_dump() == {
        "precision": 0.5,
        "recall": 1 / 3,
        "f1": 0.4,
        "true_positive": 1,
        "predicted": 2,
        "expected": 3,
    }
    assert score(set(), set()).f1 == 1
    assert score(set(), {"a"}).f1 == 0


def test_rss_platform_units_are_explicit() -> None:
    """ru_maxrss bytes and KiB produce the same byte quantity, never a stage delta."""
    assert rss_bytes(100, "darwin") == 100
    assert rss_bytes(100, "linux") == 102400
    with pytest.raises(ValueError, match="unqualified"):
        rss_bytes(100, "unknown")


@pytest.mark.parametrize(
    "changes",
    [{"assets": 709}, {"assets": 5000}, {"prefix": 65}, {"phases": ("hot", "cold", "incremental")}],
)
def test_manifest_rejects_capacity_and_unfrozen_phase_order(changes: dict[str, object]) -> None:
    """The offline runner cannot increase existing complete-set capacity or reorder stages."""
    with pytest.raises(ValidationError):
        Workload.model_validate({**Workload().model_dump(), **changes})


def test_invalid_dimensions_and_scope_are_rejected() -> None:
    """No implicit reshape, duplicate identity or gold alignment ambiguity is permitted."""
    case = case_for((("a", (1.0, 0.0)), ("b", (0.0, 1.0))))
    with pytest.raises(ValueError, match="prefix_exceeds"):
        normalized(case.model_copy(update={"prefix": 3}))
    with pytest.raises(ValueError, match="unique"):
        normalized(case.model_copy(update={"points": (case.points[0], case.points[0])}))
    with pytest.raises(ValidationError, match="sorted_unique"):
        NumericInput.model_validate({**case.model_dump(), "targets": ("b", "a")})


def test_dbscan_self_and_insufficient_are_explicit() -> None:
    """A singleton includes itself; insufficient raw labels never become published outliers."""
    case = case_for((("a", (1.0, 1.0)),), eps=0.0, min_samples=1)
    samples = normalized(case)
    assert decisions(samples, ((0.9999999,),), case).labels == (0,)
    report = compare(case.model_copy(update={"min_samples": 2, "cluster_gold": (-1,)}))
    assert report.f64.labels == report.faiss.labels == (-1,)
    assert report.f64.noise == report.faiss.noise == ()
    for metrics in (report.f64_quality, report.faiss_quality):
        assert metrics.noise != "not_available"
        assert (metrics.noise.predicted, metrics.noise.expected) == (0, 0)
