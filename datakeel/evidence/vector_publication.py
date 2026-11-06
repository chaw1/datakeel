# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Create one replayable pending bundle without exposing any new fact prematurely."""

from datakeel.core.evidence_cache import (
    EvidenceCacheEntry,
    EvidenceCacheKey,
    EvidenceInput,
    KnowledgeBundle,
)
from datakeel.core.evidence_execution import (
    EvidenceExecutionContext,
    ExtractionCounts,
    PendingExtraction,
)
from datakeel.core.evidence_models import Assertion, ExtractorRef
from datakeel.core.models import AssetRef, LineageEvent, new_id
from datakeel.core.vector_models import vector_hash
from datakeel.core.vector_results import (
    VectorCacheProduct,
    VectorNodeReport,
    VectorPair,
    VectorSample,
    VectorSetOutput,
)
from datakeel.evidence.vector_duplicate import pair_drafts
from datakeel.evidence.vector_set_publication import set_drafts
from datakeel.pipeline.models import Node


def vector_publication(
    context: EvidenceExecutionContext,
    node: Node,
    products: tuple[VectorCacheProduct, ...],
    samples: tuple[VectorSample, ...],
    report: VectorNodeReport,
    pairs: tuple[VectorPair, ...] | VectorSetOutput = (),
) -> PendingExtraction:
    """Record canonical compute identity separately from assertion projection identity."""
    event_id = new_id()
    findings = pairs.findings if isinstance(pairs, VectorSetOutput) else ()
    scope = pairs.scope if isinstance(pairs, VectorSetOutput) else None
    pairs = () if isinstance(pairs, VectorSetOutput) else pairs
    drafts = (
        pair_drafts(samples, pairs)
        if node.operator == "evidence.semantic_duplicate"
        else set_drafts(samples, findings, str(node.operator))
    )
    assertions = tuple(
        Assertion(**draft.model_dump(), producer_event_id=event_id, run_id=context.task_id)
        for draft in drafts
    )
    entries = _entries(
        samples, assertions, report.canonical_hash or vector_hash(None), str(node.operator)
    )
    event = LineageEvent(
        event_id=event_id,
        idempotency_key=f"shard:{context.shard_id}:evidence:{node.id}",
        event_type="COMPLETE",
        operator=str(node.operator),
        source_module="evidence",
        source_ref=context.task_id,
        inputs=[sample.subject for sample in samples],
        outputs=[AssetRef(asset_type="knowledge_bundle", asset_id=event_id, version="1.0")],
        params={
            "run_id": context.task_id,
            "node_id": node.id,
            "mode": "fake",
            "fake_version": "we-e2-fake-v1",
            "contract": "we-e1-v1",
            "parameters": node.params,
        },
        quality=_quality(report).model_dump(mode="json"),
    )
    return PendingExtraction(
        event=event,
        bundle=KnowledgeBundle(
            run_id=context.task_id,
            assertions=assertions,
            cache_entries=entries,
            vector_products=products,
            vector_samples=samples,
            vector_pairs=pairs,
            vector_findings=findings,
            vector_scope=scope,
        ),
    )


def _entries(
    samples: tuple[VectorSample, ...],
    assertions: tuple[Assertion, ...],
    canonical_hash: str,
    operator: str,
) -> tuple[EvidenceCacheEntry, ...]:
    if operator == "evidence.vector_embed":
        return ()
    extractor = ExtractorRef(
        id=operator,
        version="we-e2-fake-v1" if operator == "evidence.semantic_duplicate" else "we-e3-sets-v1",
    )
    inputs = tuple(
        EvidenceInput(role=sample.subject.asset_id, content_revision=sample.content_revision)
        for sample in samples
    )
    key = EvidenceCacheKey(
        inputs=inputs,
        extractor=extractor,
        lexicon_hash=vector_hash(None),
        near_duplicate_hash=canonical_hash,
    )
    return (
        tuple(
            EvidenceCacheEntry(
                subject=sample.subject,
                key=key,
                assertion_ids=tuple(
                    item.id for item in assertions if item.subject == sample.subject
                ),
            )
            for sample in samples
        )
        if inputs
        else ()
    )


def _quality(report: VectorNodeReport) -> ExtractionCounts:
    return ExtractionCounts(
        inputs=report.counts.input,
        extracted=report.counts.eligible - report.eligible_cache_hits,
        failed=report.counts.failed,
        skipped_cached=report.eligible_cache_hits,
        vector=report,
    )
