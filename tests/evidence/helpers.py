# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Synthetic extraction fixtures with explicit versioned provenance."""

from datakeel.core.evidence_cache import (
    EvidenceCacheEntry,
    EvidenceCacheKey,
    EvidenceInput,
    KnowledgeBundle,
)
from datakeel.core.evidence_models import Assertion, EvidenceAnchor, EvidenceValue, ExtractorRef
from datakeel.core.models import AssetRef, LineageEvent


def extraction_event(
    run: str = "run-one", version: str = "1", content: str = "a", *, cache: bool = True
) -> LineageEvent:
    """Build a valid run containing one image observation and its optional cache slot."""
    subject = AssetRef(asset_type="file", asset_id="image", version="source-version")
    extractor = ExtractorRef(id="evidence.image_phash", version=version)
    assertion = Assertion(
        id=f"assertion-{run}",
        subject=subject,
        predicate="corrupt",
        object=EvidenceValue(value="absent"),
        extractor=extractor,
        anchors=(EvidenceAnchor(asset_ref=subject, content_revision=content * 64),),
        producer_event_id=f"event-{run}",
        run_id=run,
    )
    key = EvidenceCacheKey(
        inputs=(EvidenceInput(role="image", content_revision=content * 64),),
        extractor=extractor,
        lexicon_hash="c" * 64,
        near_duplicate_hash="d" * 64,
    )
    bundle = KnowledgeBundle(
        run_id=run,
        assertions=(assertion,),
        cache_entries=(
            EvidenceCacheEntry(
                subject=subject,
                key=key,
                assertion_ids=(assertion.id,),
            ),
        )
        if cache
        else (),
    )
    return LineageEvent(
        event_id=f"event-{run}",
        idempotency_key=f"extract:{run}",
        event_type="COMPLETE",
        inputs=[subject],
        outputs=[AssetRef(asset_type="knowledge_bundle", asset_id=f"bundle-{run}", version="1")],
        operator="evidence.image_phash",
        source_module="evidence",
        params={"run_id": run, "knowledge_bundle": bundle.model_dump(mode="json")},
    )


def fixture_bundle(event: LineageEvent) -> KnowledgeBundle:
    """Read the caller fixture bundle before content-addressed publication."""
    return KnowledgeBundle.model_validate(event.params["knowledge_bundle"])
