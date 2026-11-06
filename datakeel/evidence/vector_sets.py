# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Exact F64 precomputed DBSCAN and bounded relative coverage over recorded F32 vectors."""

import math

from datakeel.core.models import AssetRef
from datakeel.core.vector_measurements import (
    ClusterMeasurement,
    CoverageMeasurement,
    OutlierMeasurement,
)
from datakeel.core.vector_models import ClusterParams, VectorError, VectorScope, vector_hash
from datakeel.core.vector_results import VectorFinding, VectorSample
from datakeel.evidence.vector_parameters import CoverageParams


def cosine(left: VectorSample, right: VectorSample) -> float:
    """Accumulate canonical F32 coordinates in F64 with a closed cosine range."""
    if len(left.vector) != len(right.vector):
        msg = "vector_dimension_mismatch"
        raise VectorError(msg)
    dot = math.fsum(a * b for a, b in zip(left.vector, right.vector, strict=True))
    norm = math.sqrt(math.fsum(a * a for a in left.vector)) * math.sqrt(
        math.fsum(b * b for b in right.vector)
    )
    return max(-1.0, min(1.0, dot / norm))


def dbscan(
    samples: tuple[VectorSample, ...], params: ClusterParams
) -> tuple[tuple[VectorSample, ...], tuple[int, ...], tuple[bool, ...]]:
    """Precompute inclusive neighborhoods, visit assets in order and assign borders once."""
    valid = tuple(
        sorted((s for s in samples if s.failure is None), key=lambda s: s.subject.asset_id)
    )
    if (
        len(samples) > params.max_samples
        or len(valid) * (len(valid) - 1) // 2 > params.max_candidate_pairs
    ):
        msg = "vector_capacity_exceeded"
        raise VectorError(msg)
    neighbors = _neighborhoods(valid, params.eps)
    core = tuple(len(group) >= params.min_samples for group in neighbors)
    labels = [-1] * len(valid)
    cluster = 0
    for index in range(len(valid)):
        if labels[index] != -1 or not core[index]:
            continue
        labels[index] = cluster
        frontier = [index]
        while frontier:
            current = frontier.pop()
            for peer in sorted(neighbors[current]):
                if labels[peer] == -1:
                    labels[peer] = cluster
                    if core[peer]:
                        frontier.append(peer)
        cluster += 1
    return valid, tuple(labels), core


def cluster_findings(
    samples: tuple[VectorSample, ...], params: ClusterParams, *, outlier: bool = False
) -> tuple[VectorFinding, ...]:
    """Emit members or noise only; insufficient populations never imply outliers."""
    valid, labels, core = dbscan(samples, params)
    if len(valid) < params.min_samples:
        return ()
    config = vector_hash(
        {"contract": "we-e3-dbscan-v1", "eps": params.eps, "min_samples": params.min_samples}
    )
    members = {
        label: tuple(s.subject for s, group in zip(valid, labels, strict=True) if group == label)
        for label in set(labels) - {-1}
    }
    findings: list[VectorFinding] = []
    for sample, label, is_core in zip(valid, labels, core, strict=True):
        if outlier and label == -1:
            findings.append(
                VectorFinding(
                    subject=sample.subject.asset_id,
                    measurement=OutlierMeasurement(
                        eps=params.eps, min_samples=params.min_samples, config_hash=config
                    ),
                )
            )
        elif not outlier and label >= 0:
            group = members[label]
            findings.append(
                VectorFinding(
                    subject=sample.subject.asset_id,
                    object=AssetRef(
                        asset_type="semantic_cluster",
                        asset_id=vector_hash([group[0].asset_id, config]),
                        version=config,
                    ),
                    measurement=ClusterMeasurement(
                        eps=params.eps,
                        min_samples=params.min_samples,
                        config_hash=config,
                        role="core" if is_core else "border",
                        members=group,
                    ),
                )
            )
    return tuple(findings)


def coverage_findings(
    samples: tuple[VectorSample, ...], scope: VectorScope, params: CoverageParams
) -> tuple[VectorFinding, ...]:
    """Compare T minus R to all R; missing references make coverage unknown, never absolute."""
    by_id = {s.subject.asset_id: s for s in samples}
    members = (*scope.targets, *scope.references)
    if (
        len(by_id) != len(samples)
        or set(by_id) != {m.subject.asset_id for m in members}
        or any(
            by_id[m.subject.asset_id].subject != m.subject
            or by_id[m.subject.asset_id].content_revision != m.content_revision
            for m in members
        )
    ):
        msg = "vector_reference_scope_changed"
        raise VectorError(msg)
    references = tuple(by_id[m.subject.asset_id] for m in scope.references)
    targets = {m.subject.asset_id for m in scope.targets} - {s.subject.asset_id for s in references}
    if (
        len(samples) > params.max_samples
        or len(targets) * len(references) > params.max_reference_comparisons
    ):
        msg = "vector_capacity_exceeded"
        raise VectorError(msg)
    if not references or any(s.failure is not None for s in references):
        msg = "vector_reference_empty" if not references else "vector_reference_failed"
        raise VectorError(msg)
    findings: list[VectorFinding] = []
    for identity in sorted(targets):
        sample = by_id[identity]
        if sample.failure is not None:
            continue
        best = min(references, key=lambda ref: (-cosine(sample, ref), ref.subject.asset_id))
        similarity = cosine(sample, best)
        if similarity < params.threshold:
            findings.append(
                VectorFinding(
                    subject=identity,
                    object=best.subject,
                    measurement=CoverageMeasurement(
                        nearest=best.subject,
                        similarity=similarity,
                        threshold=params.threshold,
                        reference_digest=vector_hash(
                            [m.model_dump(mode="json") for m in scope.references]
                        ),
                        references=scope.references,
                    ),
                )
            )
    return tuple(findings)


def set_key(
    samples: tuple[VectorSample, ...],
    params: ClusterParams | CoverageParams,
    operator: str,
    scope: VectorScope | None = None,
) -> str:
    """Bind mode, full recorded output, operator, parameters and both source closures."""
    return vector_hash(
        {
            "contract": "we-e3-sets-v1",
            "mode": "fake",
            "implementation": "we-e2-fake-v1",
            "operator": operator,
            "samples": sorted(s.canonical() for s in samples),
            "params": params.model_dump(mode="json"),
            "scope": scope.model_dump(mode="json") if scope else None,
        }
    )


def set_hash(key: str, findings: tuple[VectorFinding, ...]) -> str:
    """Separate computation identity from UUID-bearing fact projection identity."""
    return vector_hash({"key": key, "findings": [f.model_dump(mode="json") for f in findings]})


def _neighborhoods(valid: tuple[VectorSample, ...], eps: float) -> list[set[int]]:
    neighbors = [{i} for i in range(len(valid))]
    for i, left in enumerate(valid):
        for j in range(i + 1, len(valid)):
            if 1.0 - cosine(left, valid[j]) <= eps:
                neighbors[i].add(j)
                neighbors[j].add(i)
    return neighbors
