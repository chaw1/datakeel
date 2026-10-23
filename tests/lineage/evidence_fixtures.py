# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Versioned synthetic near-duplicate facts for semantic projection tests."""

from datakeel.core.evidence_cache import KnowledgeBundle
from datakeel.core.evidence_models import Assertion, EvidenceAnchor, ExtractorRef
from datakeel.core.models import AssetRef, LineageEvent


def pair(left: str = "a", right: str = "b") -> Assertion:
    """Build one canonical pair with exact provenance and independent source anchors."""
    subject = AssetRef(asset_type="file", asset_id=left, version="source")
    target = AssetRef(asset_type="file", asset_id=right, version="source")
    return Assertion(
        id=f"pair-{left}-{right}",
        subject=subject,
        predicate="near_duplicate_of",
        object=target,
        distance=2,
        reason="dhash distance within threshold",
        anchors=(
            EvidenceAnchor(asset_ref=subject, content_revision="a" * 64),
            EvidenceAnchor(asset_ref=target, content_revision="b" * 64),
        ),
        extractor=ExtractorRef(id="evidence.near_duplicate", version="1"),
        producer_event_id="near-event",
        run_id="near-run",
    )


def extraction(assertions: tuple[Assertion, ...]) -> LineageEvent:
    """Declare the extraction run whose inputs support every supplied pair."""
    refs = {
        anchor.asset_ref.asset_id: anchor.asset_ref
        for assertion in assertions
        for anchor in assertion.anchors
    }
    bundle = KnowledgeBundle(run_id="near-run", assertions=assertions)
    return LineageEvent(
        event_id="near-event",
        idempotency_key="near-event",
        event_type="COMPLETE",
        operator="evidence.near_duplicate",
        inputs=list(refs.values()),
        outputs=[AssetRef(asset_type="knowledge_bundle", asset_id="bundle", version="1")],
        params={"run_id": "near-run", "knowledge_bundle": bundle.model_dump(mode="json")},
    )
