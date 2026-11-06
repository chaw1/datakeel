# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Validate recorded vector computation independently of disposable cache projections."""

from datakeel.core.evidence_cache import KnowledgeBundle
from datakeel.core.models import AssetRef, LineageEvent
from datakeel.core.vector_models import VECTOR_OPERATORS, DuplicateParams, VectorError, vector_hash
from datakeel.core.vector_results import VectorNodeReport
from datakeel.evidence.vector_duplicate import global_key, vector_counts
from datakeel.storage.vector_set_integrity import validate_set_bundle


def validate_vector_bundle(event: LineageEvent, bundle: KnowledgeBundle) -> None:
    """Verify mode, full sample status and measurement hashes before publication or replay."""
    if event.operator not in VECTOR_OPERATORS:
        if (
            bundle.vector_products
            or bundle.vector_samples
            or bundle.vector_pairs
            or bundle.vector_findings
            or bundle.vector_scope
        ):
            msg = "vector_bundle_wrong_operator"
            raise VectorError(msg)
        return
    if event.operator not in {"evidence.vector_embed", "evidence.semantic_duplicate"}:
        validate_set_bundle(event, bundle)
        return
    samples = bundle.vector_samples
    report = VectorNodeReport.model_validate(event.quality.get("vector"))
    valid = (
        event.params.get("mode") == "fake"
        and event.params.get("fake_version") == "we-e2-fake-v1"
        and report.counts == vector_counts(samples)
    )
    if event.operator == "evidence.vector_embed":
        expected = vector_hash(sorted(sample.canonical() for sample in samples))
        valid = valid and not bundle.assertions and not bundle.vector_pairs
    else:
        params = DuplicateParams.model_validate(event.params.get("parameters"))
        expected = vector_hash(
            {
                "key": global_key(samples, params),
                "pairs": [pair.model_dump(mode="json") for pair in bundle.vector_pairs],
            }
        )
        actual = {
            (item.subject.asset_id, item.object.asset_id, item.measurement)
            for item in bundle.assertions
            if isinstance(item.object, AssetRef)
        }
        pairs = {(pair.left, pair.right, pair.measurement) for pair in bundle.vector_pairs}
        valid = valid and actual == pairs
    valid = valid and report.canonical_hash == expected
    for product in bundle.vector_products:
        valid = valid and product.mode == "fake" and product.implementation == "we-e2-fake-v1"
        valid = valid and all(sample in samples for sample in product.samples)
        if product.kind == "embedding":
            valid = valid and product.key == product.samples[0].embedding_key
        else:
            valid = valid and product.samples == samples and product.pairs == bundle.vector_pairs
    if not valid:
        msg = "vector_bundle_integrity_invalid"
        raise VectorError(msg)
