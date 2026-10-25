# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Build truthful graph-run accounting from committed call traces and block outcomes."""

from collections import defaultdict
from decimal import Decimal

from datakeel.core.evidence_models import ImageRegion
from datakeel.core.harness_models import ModelCallTrace
from datakeel.core.kg_costs import known_cost
from datakeel.core.kg_execution import KGBlockFailure, KGJob, KGReport
from datakeel.core.kg_product import ProductExtraction, SchemaProposal
from datakeel.kg.aliases import same_as_drafts
from datakeel.kg.cache import extraction_identity
from datakeel.kg.identity import merge_drafts
from datakeel.kg.policy import is_external
from datakeel.storage.transcription_pricing import transcription_external


def merge_products(job: KGJob, values: list[ProductExtraction]) -> ProductExtraction:
    """Merge candidate triples across chunks and retain every distinct mention anchor."""
    entities = {entity.asset_ref.asset_id: entity for value in values for entity in value.entities}
    drafts = merge_drafts(tuple(draft for value in values for draft in value.drafts))
    proposals: dict[str, list[SchemaProposal]] = defaultdict(list)
    for value in values:
        for proposal in value.proposals:
            proposals[proposal.reason].append(proposal)
    prepared = job.prepared
    extractor = extraction_identity(
        prepared.schema_definition, prepared.profile, prepared.recording_hash
    )
    selected = tuple(entities[key] for key in sorted(entities))
    aliases = same_as_drafts(selected, drafts, prepared.schema_definition, extractor)
    return ProductExtraction(
        entities=selected,
        drafts=merge_drafts((*drafts, *aliases)),
        proposals=tuple(
            SchemaProposal.model_validate(
                {
                    "reason": reason,
                    "count": sum(item.count for item in group),
                    "samples": tuple(sample for item in group for sample in item.samples)[:20],
                    "entity_samples": tuple(
                        sample for item in group for sample in item.entity_samples
                    )[:20],
                }
            )
            for reason, group in sorted(proposals.items())
        ),
    )


def base_report(
    job: KGJob,
    products: ProductExtraction,
    failures: list[KGBlockFailure],
    traces: list[ModelCallTrace],
) -> KGReport:
    """Separate observed usage and unknown conservative charges from actual provider fees."""
    relations = [item for item in products.drafts if item.predicate != "kg.mentions"]
    unverified_entities = {
        item.subject.asset_id
        for item in products.drafts
        if item.predicate == "kg.mentions" and item.verification == "needs_review"
    }
    usages = [trace.observed_usage or trace.usage for trace in traces]
    accounted = sum((trace.cost_usd for trace in traces), start=Decimal(0))
    located = sum(
        any(isinstance(anchor.selector, ImageRegion) for anchor in item.anchors)
        for item in relations
    )
    image_relations = sum(
        any(anchor.asset_ref.asset_type == "image_transcript" for anchor in item.anchors)
        for item in relations
    )
    cloud = _cloud_traces(job, traces)
    return KGReport(
        transcriptions=job.run.report.transcriptions,
        transcription_failed=job.run.report.transcription_failed,
        located_relations=located,
        unlocated_relations=image_relations - located,
        cloud_calls=len(cloud),
        cloud_cost_usd=known_cost(cloud),
        documents=len(job.prepared.documents),
        blocks=sum(len(document.blocks) for document in job.documents)
        + job.run.report.transcription_failed,
        model_calls=len(traces),
        entities=len(products.entities),
        relations=len(relations),
        verified=sum(item.verification == "verified" for item in products.drafts),
        needs_review=sum(item.verification == "needs_review" for item in products.drafts),
        entities_verified=len(products.entities) - len(unverified_entities),
        entities_needs_review=len(unverified_entities),
        relations_verified=sum(item.verification == "verified" for item in relations),
        relations_needs_review=sum(item.verification == "needs_review" for item in relations),
        input_tokens=sum(usage.input_tokens for usage in usages),
        output_tokens=sum(usage.output_tokens for usage in usages),
        accounted_cost_usd=accounted,
        cost_usd=known_cost(traces),
        transcription_cost_usd=known_cost(traces, "transcription"),
        extraction_cost_usd=known_cost(traces, "extraction"),
        failed=sum(failure.attempted for failure in failures),
        unexecuted=sum(not failure.attempted for failure in failures),
        failures=tuple(failures),
        partial_documents=tuple(sorted({item.file_id for item in failures})),
        proposals=products.proposals,
    )


def _cloud_traces(job: KGJob, traces: list[ModelCallTrace]) -> list[ModelCallTrace]:
    return [
        trace
        for trace in traces
        if (
            transcription_external(job.prepared.transcription_profile)
            if trace.call_type == "transcription" and job.prepared.transcription_profile
            else is_external(job.prepared.profile)
        )
    ]
