# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Validate replayed set products using only recorded output, never an embedding transport."""

from datakeel.core.evidence_cache import KnowledgeBundle
from datakeel.core.models import LineageEvent
from datakeel.core.vector_models import ClusterParams, VectorError
from datakeel.core.vector_results import VectorNodeReport
from datakeel.evidence.vector_duplicate import vector_counts
from datakeel.evidence.vector_parameters import CoverageParams
from datakeel.evidence.vector_set_publication import set_drafts
from datakeel.evidence.vector_sets import cluster_findings, coverage_findings, set_hash, set_key


def validate_set_bundle(event: LineageEvent, bundle: KnowledgeBundle) -> None:
    """Check the exact findings, full closure, anchors, counts and independently hashed compute."""
    samples, scope = bundle.vector_samples, bundle.vector_scope
    params = (
        CoverageParams.model_validate(event.params.get("parameters"))
        if event.operator == "evidence.coverage_gap"
        else ClusterParams.model_validate(event.params.get("parameters"))
    )
    targets = tuple(
        s
        for s in samples
        if scope is None or s.subject.asset_id in {m.subject.asset_id for m in scope.targets}
    )
    if isinstance(params, CoverageParams):
        if scope is None:
            msg = "vector_bundle_integrity_invalid"
            raise VectorError(msg)
        findings = coverage_findings(samples, scope, params)
    else:
        findings = cluster_findings(
            samples, params, outlier=event.operator == "evidence.semantic_outlier"
        )
    expected = set_drafts(samples, findings, event.operator)
    actual = tuple(
        a.model_dump(mode="json", include=set(type(draft).model_fields))
        for a, draft in zip(bundle.assertions, expected, strict=False)
    )
    report = VectorNodeReport.model_validate(event.quality.get("vector"))
    valid = (
        event.params.get("mode") == "fake"
        and event.params.get("fake_version") == "we-e2-fake-v1"
        and report.counts == vector_counts(targets)
        and findings == bundle.vector_findings
        and len(bundle.assertions) == len(expected)
        and actual == tuple(d.model_dump(mode="json") for d in expected)
        and report.canonical_hash
        == set_hash(set_key(samples, params, event.operator, scope), findings)
        and not bundle.vector_pairs
        and tuple(event.inputs) == tuple(s.subject for s in samples)
    )
    for product in bundle.vector_products:
        valid = valid and (
            product.mode == "fake"
            and product.implementation == "we-e2-fake-v1"
            and product.kind == "global"
            and product.samples == samples
            and product.findings == findings
            and product.scope == scope
            and not product.pairs
            and product.key == set_key(samples, params, event.operator, scope)
        )
    if not valid:
        msg = "vector_bundle_integrity_invalid"
        raise VectorError(msg)
