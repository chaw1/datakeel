# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Handwritten synthetic vector goldens, independent of any evaluation corpus."""

import math
from contextlib import suppress

import pytest
from pydantic import TypeAdapter, ValidationError

from datakeel.core.models import AssetRef
from datakeel.core.vector_measurements import (
    ClusterMeasurement,
    CoverageMeasurement,
    VectorMeasurement,
)
from datakeel.core.vector_models import (
    ClusterParams,
    VectorError,
    VectorMember,
    VectorScope,
    vector_hash,
)
from datakeel.core.vector_results import VectorSample
from datakeel.evidence.vector_parameters import CoverageParams
from datakeel.evidence.vector_sets import cluster_findings, coverage_findings, dbscan, set_key
from datakeel.ontology.models import ObjectSet


def sample(identity: str, angle: float = 0, *, failed: bool = False) -> VectorSample:
    """Generate a unit-circle point rounded by the production F32 boundary."""
    return VectorSample(
        subject=AssetRef(asset_type="file", asset_id=identity, version="v1"),
        vector=() if failed else (math.cos(angle), math.sin(angle)),
        failure="synthetic_failure" if failed else None,
        content_revision=vector_hash(identity),
        embedding_key=vector_hash([identity]),
    )


def scope(targets: tuple[VectorSample, ...], refs: tuple[VectorSample, ...]) -> VectorScope:
    """Create immutable source closures from locally constructed points."""

    def members(values: tuple[VectorSample, ...]) -> tuple[VectorMember, ...]:
        return tuple(
            VectorMember(
                subject=s.subject, revision=s.content_revision, content_revision=s.content_revision
            )
            for s in sorted(values, key=lambda s: s.subject.asset_id)
        )

    return VectorScope(targets=members(targets), references=members(refs))


@pytest.mark.parametrize(
    ("size", "minimum", "labels"),
    [(0, 1, ()), (1, 1, (0,)), (1, 2, (-1,)), (2, 2, (0, 0)), (2, 3, (-1, -1))],
)
def test_dbscan_empty_single_double_include_self(
    size: int, minimum: int, labels: tuple[int, ...]
) -> None:
    """Self counts toward density and insufficient never emits outlier claims."""
    points = tuple(sample(str(i)) for i in range(size))
    params = ClusterParams(eps=0.0, min_samples=minimum)
    assert dbscan(points, params)[1] == labels
    assert cluster_findings(points, params, outlier=True) == ()


def test_dbscan_core_border_noise_stable_permutation() -> None:
    """A border remains a member; a distant sample alone is noise."""
    points = tuple(
        sample(key, angle)
        for key, angle in [("a", 0), ("b", 0.1), ("c", 0.2), ("d", 0.35), ("z", 2)]
    )
    params = ClusterParams(eps=0.012, min_samples=3)
    valid, labels, core = dbscan(points, params)
    assert tuple(s.subject.asset_id for s in valid) == ("a", "b", "c", "d", "z")
    assert labels == (0, 0, 0, 0, -1)
    assert core == (False, True, True, False, False)
    findings = cluster_findings(points, params)
    assert findings == cluster_findings(tuple(reversed(points)), params)
    assert [f.subject for f in cluster_findings(points, params, outlier=True)] == ["z"]
    assert len({f.object for f in findings}) == 1
    assert all(isinstance(f.measurement, ClusterMeasurement) for f in findings)
    assert findings[0].object == cluster_findings(points[:-1], params)[0].object


def test_dbscan_distance_boundary_and_border_first_cluster() -> None:
    """Inclusive distance binds an exact pair; a shared noncore border belongs to the first core."""
    left = sample("a")
    right = sample("b", math.pi / 2).model_copy(update={"vector": (0.0, 1.0)})
    assert dbscan((left, right), ClusterParams(eps=1.0, min_samples=2))[1] == (0, 0)
    # Dense ends, a shared border with three neighbors (including itself), minimum four.
    points = tuple(
        sample(k, a)
        for k, a in [
            ("a", -0.4),
            ("b", -0.5),
            ("c", -0.51),
            ("d", -0.52),
            ("m", 0),
            ("u", 0.4),
            ("v", 0.5),
            ("w", 0.51),
            ("x", 0.52),
        ]
    )
    _, labels, core = dbscan(points, ClusterParams(eps=0.081, min_samples=4))
    assert not core[4]
    assert labels == (0, 0, 0, 0, 0, 1, 1, 1, 1)


def test_coverage_union_difference_tie_and_relative_threshold() -> None:
    """Overlap is embedded once and never scored; equal nearest references use asset ID."""
    a, b, t = sample("a"), sample("b"), sample("t", math.pi)
    frozen = scope((a, t), (a, b))
    params = CoverageParams(reference=ObjectSet(), threshold=0.5, max_reference_comparisons=2)
    findings = coverage_findings((t, b, a), frozen, params)
    assert [f.subject for f in findings] == ["t"]
    measured = findings[0].measurement
    assert isinstance(measured, CoverageMeasurement)
    assert measured.nearest == a.subject
    assert measured.similarity == -1.0
    assert len(measured.references) == 2
    assert coverage_findings((a, b), scope((a,), (a, b)), params) == ()
    changed = frozen.model_copy(update={"references": frozen.references[:1]})
    assert set_key((a, b, t), params, "evidence.coverage_gap", frozen) != set_key(
        (a, b, t), params, "evidence.coverage_gap", changed
    )
    with pytest.raises(VectorError, match="capacity"):
        coverage_findings(
            (t, a, b), frozen, params.model_copy(update={"max_reference_comparisons": 1})
        )


@pytest.mark.parametrize("failed", [False, True])
def test_coverage_empty_or_failed_reference_is_unknown(*, failed: bool) -> None:
    """An empty or incomplete R cannot yield a successful coverage claim."""
    t = sample("t")
    r = sample("r", failed=True)
    refs = (r,) if failed else ()
    with pytest.raises(VectorError, match="vector_reference_"):
        coverage_findings((t, *refs), scope((t,), refs), CoverageParams(reference=ObjectSet()))


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_set_parameters_forbid_nonfinite(value: float) -> None:
    """Configuration and every measurement reject nonfinite serialized values."""
    with pytest.raises(ValidationError):
        ClusterParams(eps=value)
    with pytest.raises(ValidationError):
        CoverageParams(reference=ObjectSet(), threshold=value)


@pytest.mark.parametrize(
    "kind", ["cosine_duplicate", "cluster_config", "outlier_config", "coverage"]
)
@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_measurement_union_rejects_nonfinite(kind: str, value: float) -> None:
    """Every discriminated result branch rejects nonfinite numeric facts at deserialization."""
    a = sample("a")
    r = sample("r")
    common = {"eps": value, "min_samples": 2, "config_hash": "a" * 64}
    measurements = {
        "cosine_duplicate": {"type": kind, "similarity": value, "threshold": 0.5},
        "cluster_config": {
            "type": kind,
            **common,
            "role": "core",
            "members": [a.subject.model_dump()],
        },
        "outlier_config": {"type": kind, **common},
        "coverage": {
            "type": kind,
            "nearest": r.subject.model_dump(),
            "similarity": value,
            "threshold": 0.5,
            "reference_digest": "a" * 64,
            "references": [m.model_dump() for m in scope((a,), (r,)).references],
        },
    }
    with pytest.raises(ValidationError):
        TypeAdapter(VectorMeasurement).validate_python(measurements[kind])


def test_dbscan_insufficient_observable() -> None:
    """An undersized population produces no noise claim even though all labels are unassigned."""
    assert cluster_findings((sample("a"),), ClusterParams(min_samples=2), outlier=True) == ()


def test_cluster_id_uses_minimum_member_and_configuration() -> None:
    """Stable cluster references use the smallest member and frozen DBSCAN configuration."""
    points = (sample("z"), sample("a"))
    params = ClusterParams(eps=0.0, min_samples=2)
    finding = cluster_findings(points, params)[0]
    config = vector_hash({"contract": "we-e3-dbscan-v1", "eps": 0.0, "min_samples": 2})
    assert finding.object == AssetRef(
        asset_type="semantic_cluster", asset_id=vector_hash(["a", config]), version=config
    )
    assert (
        cluster_findings(points, params.model_copy(update={"eps": 0.1}))[0].object != finding.object
    )


def test_gap_difference_comparison_count_observable() -> None:
    """Complete overlap has zero reference comparisons and no candidate."""
    a = sample("a")
    output = None
    with suppress(VectorError):
        output = coverage_findings(
            (a,),
            scope((a,), (a,)),
            CoverageParams(reference=ObjectSet(), max_reference_comparisons=0),
        )
    assert output == ()


def test_gap_failed_reference_observable() -> None:
    """A failed reference is an unknown closure even when another reference is valid."""
    t, a, b = sample("t"), sample("a"), sample("b", failed=True)
    reason = None
    try:
        coverage_findings((t, a, b), scope((t,), (a, b)), CoverageParams(reference=ObjectSet()))
    except VectorError as error:
        reason = error.reason
    assert reason == "vector_reference_failed"
