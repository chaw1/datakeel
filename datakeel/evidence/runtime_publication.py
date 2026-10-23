# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Bind typed operator observations to a deferred authoritative COMPLETE event."""

from datakeel.core.evidence_cache import KnowledgeBundle
from datakeel.core.evidence_execution import EvidenceExecutionContext, PendingExtraction
from datakeel.core.evidence_models import Assertion
from datakeel.core.models import AssetRef, LineageEvent, new_id
from datakeel.evidence.runtime_compute import NodeExtraction
from datakeel.evidence.runtime_inputs import subject_ref
from datakeel.pipeline.models import Node


def publication(
    context: EvidenceExecutionContext, node: Node, result: NodeExtraction, elapsed: float
) -> PendingExtraction:
    """Create provenance without publishing anything before the lease is fenced."""
    event_id = new_id()
    assertions = tuple(
        Assertion(
            **dict(draft),
            producer_event_id=event_id,
            run_id=context.task_id,
        )
        for draft in result.drafts
    )
    refs = [subject_ref(file) for file in result.files]
    for assertion in assertions:
        refs.extend(anchor.asset_ref for anchor in assertion.anchors)
        if isinstance(assertion.object, AssetRef):
            refs.append(assertion.object)
    unique = {(ref.namespace, ref.asset_type, ref.asset_id, ref.version): ref for ref in refs}
    counts = result.counts.model_copy(update={"elapsed_seconds": elapsed})
    event = LineageEvent(
        event_id=event_id,
        idempotency_key=f"shard:{context.shard_id}:evidence:{node.id}",
        event_type="COMPLETE",
        operator=str(node.operator),
        source_module="evidence",
        source_ref=context.task_id,
        inputs=list(unique.values()),
        outputs=[AssetRef(asset_type="knowledge_bundle", asset_id=event_id, version="1.0")],
        params={"run_id": context.task_id, "node_id": node.id},
        quality=counts.model_dump(mode="json"),
    )
    by_subject: dict[AssetRef, list[str]] = {}
    for assertion in assertions:
        by_subject.setdefault(assertion.subject, []).append(assertion.id)
    entries = tuple(
        entry.model_copy(update={"assertion_ids": tuple(by_subject.get(entry.subject, ()))})
        for entry in result.entries
    )
    return PendingExtraction(
        event=event,
        bundle=KnowledgeBundle(
            run_id=context.task_id,
            assertions=assertions,
            cache_entries=entries,
        ),
    )
