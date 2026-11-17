# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Compute bounded set candidates with disposable global cache reuse and typed status."""

from datakeel.core.models import BoundaryModel
from datakeel.core.vector_models import (
    ClusterParams,
    VectorCounts,
    VectorError,
    VectorImpl,
    VectorMode,
    VectorScope,
)
from datakeel.core.vector_results import (
    VectorCacheProduct,
    VectorFinding,
    VectorNodeReport,
    VectorSample,
    VectorSetOutput,
)
from datakeel.evidence.vector_duplicate import vector_counts
from datakeel.evidence.vector_parameters import CoverageParams
from datakeel.evidence.vector_sets import cluster_findings, coverage_findings, set_hash, set_key
from datakeel.pipeline.models import Node
from datakeel.storage.database import Database
from datakeel.storage.vector_cache import vector_cached


class SetComputation(BoundaryModel):
    """Carry pending facts even when a temporary input forbids caching the computation."""

    products: tuple[VectorCacheProduct, ...]
    output: VectorSetOutput
    report: VectorNodeReport


def compute_set(
    db: Database,
    samples: tuple[VectorSample, ...],
    node: Node,
    scope: VectorScope | None,
    *,
    mode: VectorMode = "fake",
    implementation: VectorImpl = "we-e2-fake-v1",
) -> SetComputation:
    """Reuse only a full set key and retain target-only counts for relative coverage."""
    params = (
        CoverageParams.model_validate(node.params)
        if node.operator == "evidence.coverage_gap"
        else ClusterParams.model_validate(node.params)
    )
    targets = tuple(
        s
        for s in samples
        if scope is None or s.subject.asset_id in {m.subject.asset_id for m in scope.targets}
    )
    counts = vector_counts(targets)
    key = set_key(
        samples, params, str(node.operator), scope, mode=mode, implementation=implementation
    )
    cached = vector_cached(db, key, "global", mode=mode, implementation=implementation)
    findings = cached.findings if cached else _resolve_findings(samples, scope, params, node)
    insufficient = isinstance(params, ClusterParams) and counts.eligible < params.min_samples
    if counts.input and not counts.eligible:
        msg = "vector_all_inputs_failed"
        raise VectorError(msg, counts)
    products = (
        ()
        if any(s.temporary for s in samples)
        else (
            VectorCacheProduct(
                key=key,
                mode=mode,
                implementation=implementation,
                kind="global",
                samples=samples,
                findings=findings,
                scope=scope,
            ),
        )
    )
    return SetComputation(
        products=products,
        output=VectorSetOutput(findings=findings, scope=scope),
        report=_report(
            counts,
            set_hash(key, findings),
            insufficient=insufficient,
            cached=bool(cached),
            mode=mode,
            implementation=implementation,
        ),
    )


def _resolve_findings(
    samples: tuple[VectorSample, ...],
    scope: VectorScope | None,
    params: CoverageParams | ClusterParams,
    node: Node,
) -> tuple[VectorFinding, ...]:
    if isinstance(params, CoverageParams):
        if scope is None:
            msg = "vector_reference_scope_missing"
            raise VectorError(msg)
        return coverage_findings(samples, scope, params)
    return cluster_findings(samples, params, outlier=node.operator == "evidence.semantic_outlier")


def _report(
    counts: VectorCounts,
    canonical_hash: str,
    *,
    insufficient: bool,
    cached: bool,
    mode: VectorMode,
    implementation: VectorImpl,
) -> VectorNodeReport:
    return VectorNodeReport(
        mode=mode,
        fake_version=implementation,
        status="insufficient"
        if insufficient
        else "partial_success"
        if counts.failed
        else "success",
        reason="vector_insufficient_samples" if insufficient else None,
        counts=counts,
        canonical_hash=canonical_hash,
        cache_hits=counts.input if cached else 0,
        eligible_cache_hits=counts.eligible if cached else 0,
    )
