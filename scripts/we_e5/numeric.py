# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""IndexFlatIP over shared normalized F32 coordinates, with unaltered F64 production calls."""

from __future__ import annotations

import importlib
import math
from typing import TYPE_CHECKING, Protocol, cast

import numpy as np

from datakeel.core.models import AssetRef
from datakeel.core.vector_models import (
    ClusterParams,
    DuplicateParams,
    VectorMember,
    VectorScope,
    vector_hash,
)
from datakeel.core.vector_results import VectorSample
from datakeel.evidence.vector_duplicate import direct_pairs
from datakeel.evidence.vector_parameters import CoverageParams
from datakeel.evidence.vector_sets import cosine, coverage_findings, dbscan
from datakeel.ontology.models import ObjectSet
from scripts.we_e5.models import MAX_COMPARISONS, MAX_SAMPLES, BackendResult, NumericInput

if TYPE_CHECKING:
    from numpy.typing import NDArray


class FlatIndex(Protocol):
    """Describe the narrow exact-index adapter without importing it into product code."""

    def add(self, values: NDArray[np.float32]) -> None:
        """Insert the complete canonical normalized matrix."""
        ...

    def search(
        self, values: NDArray[np.float32], count: int
    ) -> tuple[NDArray[np.float32], NDArray[np.int64]]:
        """Search every row; this offline comparison never truncates to approximate neighbors."""
        ...


class Faiss(Protocol):
    """Type the small development-only FAISS boundary."""

    def IndexFlatIP(self, dimensions: int) -> FlatIndex:  # noqa: N802  # Upstream API spelling.
        """Construct an exact inner-product index."""
        ...

    def omp_set_num_threads(self, count: int) -> None:
        """Bound internal computation to the declared local worker count."""
        ...


def normalized(case: NumericInput) -> tuple[VectorSample, ...]:
    """Sort unique IDs, apply the same prefix, reject nonfinite/zero, and normalize once."""
    points = sorted(case.points, key=lambda point: point.asset_id)
    ids = [p.asset_id for p in points]
    if (
        not points
        or len(ids) != len(set(ids))
        or set(ids) != set(case.targets) | set(case.references)
    ):
        msg = "nonempty_unique_closed_points_required"
        raise ValueError(msg)
    if (
        len(points) > MAX_SAMPLES
        or len(points) * (len(points) - 1) // 2 > MAX_COMPARISONS
        or len(case.targets) * (len(case.targets) - 1) // 2 > MAX_COMPARISONS
    ):
        msg = "vector_capacity_exceeded"
        raise ValueError(msg)
    if len(case.targets) * len(case.references) > MAX_COMPARISONS:
        msg = "vector_capacity_exceeded"
        raise ValueError(msg)
    if case.prefix < 1 or len({len(p.values) for p in points}) != 1:
        msg = "invalid_prefix_or_dimensions"
        raise ValueError(msg)
    if any(len(p.values) < case.prefix for p in points):
        msg = "prefix_exceeds_dimensions"
        raise ValueError(msg)
    matrix = np.asarray([p.values for p in points], dtype=np.float32)
    if not np.isfinite(matrix).all():
        msg = "nonfinite_f32"
        raise ValueError(msg)
    matrix = matrix[:, : case.prefix]
    norms = np.linalg.norm(matrix.astype(np.float64), axis=1)
    if not np.isfinite(norms).all() or not norms.all():
        msg = "zero_vector_after_prefix"
        raise ValueError(msg)
    matrix = np.ascontiguousarray(matrix / norms[:, None], dtype=np.float32)
    return tuple(
        VectorSample(
            subject=AssetRef(asset_type="file", asset_id=identity, version="synthetic-v1"),
            content_revision=vector_hash(identity),
            embedding_key=vector_hash([identity]),
            vector=tuple(float(v) for v in row),
        )
        for identity, row in zip(ids, matrix, strict=True)
    )


def faiss_scores(samples: tuple[VectorSample, ...]) -> tuple[tuple[float, ...], ...]:
    """Index and query identical normalized F32 bytes; restore stable ID order after search."""
    faiss = cast("Faiss", importlib.import_module("faiss"))
    faiss.omp_set_num_threads(1)
    matrix = np.ascontiguousarray([s.vector for s in samples], dtype=np.float32)
    index = faiss.IndexFlatIP(matrix.shape[1])
    index.add(matrix)
    distances, neighbors = index.search(matrix, len(samples))
    return tuple(
        tuple(float(score) for _, score in sorted(zip(order, scores, strict=True)))
        for scores, order in zip(distances, neighbors, strict=True)
    )


def f64_scores(samples: tuple[VectorSample, ...]) -> tuple[tuple[float, ...], ...]:
    """Use the production F64 cosine over exactly the same normalized F32 values."""
    return tuple(tuple(cosine(left, right) for right in samples) for left in samples)


def _cluster(scores: tuple[tuple[float, ...], ...], case: NumericInput) -> tuple[int, ...]:
    neighbors = [
        tuple(j for j, similarity in enumerate(row) if j == i or 1.0 - similarity <= case.eps)
        for i, row in enumerate(scores)
    ]
    core = [len(group) >= case.min_samples for group in neighbors]
    labels = [-1] * len(scores)
    cluster = 0
    for i in range(len(scores)):
        if labels[i] != -1 or not core[i]:
            continue
        labels[i] = cluster
        frontier = [i]
        while frontier:
            for peer in neighbors[frontier.pop()]:
                if labels[peer] == -1:
                    labels[peer] = cluster
                    if core[peer]:
                        frontier.append(peer)
        cluster += 1
    return tuple(labels)


def _published_noise(
    ids: tuple[str, ...], labels: tuple[int, ...], min_samples: int
) -> tuple[str, ...]:
    """Match production: insufficient populations never publish raw DBSCAN labels as outliers."""
    if len(ids) < min_samples:
        return ()
    return tuple(identity for identity, label in zip(ids, labels, strict=True) if label == -1)


def decisions(
    samples: tuple[VectorSample, ...], scores: tuple[tuple[float, ...], ...], case: NumericInput
) -> BackendResult:
    """Freeze inclusive duplicate/DBSCAN, strict gap and exact-score asset-ID ties."""
    ids = tuple(s.subject.asset_id for s in samples)
    positions = {identity: i for i, identity in enumerate(ids)}
    targets = tuple(sorted(case.targets))
    refs = tuple(sorted(case.references))
    pairs = tuple(
        (left, right)
        for i, left in enumerate(targets)
        for right in targets[i + 1 :]
        if scores[positions[left]][positions[right]] >= case.threshold
    )
    kept: list[str] = []
    removed: list[tuple[str, str]] = []
    for identity in targets:
        candidates = sorted(
            kept, key=lambda peer: (-scores[positions[identity]][positions[peer]], peer)
        )
        if candidates and scores[positions[identity]][positions[candidates[0]]] >= case.threshold:
            removed.append((identity, candidates[0]))
        else:
            kept.append(identity)
    target_scores = tuple(
        tuple(scores[positions[t]][positions[p]] for p in targets) for t in targets
    )
    labels = _cluster(target_scores, case)
    gaps: list[tuple[str, str]] = []
    for identity in sorted(set(targets) - set(refs)):
        if refs:
            best = min(refs, key=lambda peer: (-scores[positions[identity]][positions[peer]], peer))
            if scores[positions[identity]][positions[best]] < case.gap_threshold:
                gaps.append((identity, best))
    return BackendResult(
        pairs=pairs,
        removed=tuple(t for t, _ in removed),
        representatives=tuple(removed),
        labels=labels,
        noise=_published_noise(targets, labels, case.min_samples),
        gaps=tuple(gaps),
        reduction=len(removed) / len(targets) if targets else 0.0,
    )


def production_result(
    samples: tuple[VectorSample, ...], scores: tuple[tuple[float, ...], ...], case: NumericInput
) -> BackendResult:
    """Evaluate production direct pairs and DBSCAN, retaining the shared offline greedy view."""
    targets = tuple(s for s in samples if s.subject.asset_id in case.targets)
    result = decisions(samples, scores, case)
    pairs = direct_pairs(targets, DuplicateParams(threshold=case.threshold))
    _, labels, _ = dbscan(targets, ClusterParams(eps=case.eps, min_samples=case.min_samples))
    gaps = _production_gaps(samples, case)
    ids = tuple(s.subject.asset_id for s in targets)
    return result.model_copy(
        update={
            "pairs": tuple((p.left, p.right) for p in pairs),
            "gaps": gaps,
            "labels": labels,
            "noise": _published_noise(ids, labels, case.min_samples),
        }
    )


def _production_gaps(
    samples: tuple[VectorSample, ...], case: NumericInput
) -> tuple[tuple[str, str], ...]:
    if not case.references:
        return ()

    def members(ids: tuple[str, ...]) -> tuple[VectorMember, ...]:
        return tuple(
            VectorMember(
                subject=s.subject, revision=s.content_revision, content_revision=s.content_revision
            )
            for s in samples
            if s.subject.asset_id in ids
        )

    scope = VectorScope(targets=members(case.targets), references=members(case.references))
    findings = coverage_findings(
        samples, scope, CoverageParams(reference=ObjectSet(), threshold=case.gap_threshold)
    )
    return tuple((f.subject, f.object.asset_id) for f in findings if f.object is not None)


def float_differences(
    left: tuple[tuple[float, ...], ...], right: tuple[tuple[float, ...], ...]
) -> dict[str, float | int]:
    """Report raw accumulation differences without epsilon-based decision reconciliation."""
    values = [
        abs(a - b) for x, y in zip(left, right, strict=True) for a, b in zip(x, y, strict=True)
    ]
    return {
        "compared": len(values),
        "different": sum(v != 0 for v in values),
        "max_absolute": max(values, default=0.0),
        "mean_absolute": math.fsum(values) / len(values),
    }
