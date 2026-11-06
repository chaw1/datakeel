# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Compute bounded set candidates with disposable global cache reuse and typed status."""

from datakeel.core.models import BoundaryModel
from datakeel.core.vector_models import ClusterParams, VectorCounts, VectorError, VectorScope
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
    key = set_key(samples, params, str(node.operator), scope)
    cached = vector_cached(db, key, "global")
    if isinstance(params, CoverageParams):
        if scope is None:
            msg = "vector_reference_scope_missing"
            raise VectorError(msg)
        findings = cached.findings if cached else coverage_findings(samples, scope, params)
    else:
        findings = (
            cached.findings
            if cached
            else cluster_findings(
                samples, params, outlier=node.operator == "evidence.semantic_outlier"
            )
        )
    insufficient = isinstance(params, ClusterParams) and counts.eligible < params.min_samples
    if counts.input and not counts.eligible:
        msg = "vector_all_inputs_failed"
        raise VectorError(msg, counts)
    products = (
        ()
        if any(s.temporary for s in samples)
        else (
            VectorCacheProduct(
                key=key, kind="global", samples=samples, findings=findings, scope=scope
            ),
        )
    )
    return SetComputation(
        products=products,
        output=VectorSetOutput(findings=findings, scope=scope),
        report=_report(counts, key, findings, insufficient=insufficient, cached=bool(cached)),
    )


def _report(
    counts: VectorCounts,
    key: str,
    findings: tuple[VectorFinding, ...],
    *,
    insufficient: bool,
    cached: bool,
) -> VectorNodeReport:
    return VectorNodeReport(
        status="insufficient"
        if insufficient
        else "partial_success"
        if counts.failed
        else "success",
        reason="vector_insufficient_samples" if insufficient else None,
        counts=counts,
        canonical_hash=set_hash(key, findings),
        cache_hits=counts.input if cached else 0,
        eligible_cache_hits=counts.eligible if cached else 0,
    )
