# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Execute the real schema/endpoint/grounding pipeline on each independently labelled case."""

from __future__ import annotations

import hashlib
from time import perf_counter
from typing import TYPE_CHECKING

from datakeel.core.evidence_models import ExtractorRef
from datakeel.core.kg_errors import KGExtractionError
from datakeel.core.kg_eval_models import (
    KGBlockedRelation,
    KGCase,
    KGEvalFailure,
    RecordedUsage,
    ScoredEntity,
    ScoredRecord,
)
from datakeel.core.kg_product import KGSource, ProductExtraction
from datakeel.core.models import AssetRef, BoundaryModel
from datakeel.kg.assembly import assemble_extraction
from datakeel.kg.extractors import checked_extract
from datakeel.kg.text import chunk_text, decode_text
from datakeel.kg_eval.projection import blocked_relations, product_predictions, raw_relations

if TYPE_CHECKING:
    from datakeel.core.kg_contracts import ExtractionProfile, KGSchema
    from datakeel.core.kg_eval_models import ScoredRelation
    from datakeel.kg.extractors import ExtractorAdapter


class CaseExecution(BoundaryModel):
    """Keep independent raw predictions next to actual candidate projections."""

    raw: ScoredRecord
    product: ScoredRecord
    blocked: tuple[KGBlockedRelation, ...]
    failures: tuple[KGEvalFailure, ...]


def _source(case: KGCase, profile: ExtractionProfile, text: str) -> KGSource:
    return KGSource(
        dataset_id="kg-evaluation",
        dataset_version_id="kg-evaluation-v1",
        file=AssetRef(asset_type="file", asset_id=case.id, version="kg-evaluation-v1"),
        text=text,
        content_revision=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        extractor=ExtractorRef(id=profile.extractor, version=profile.model),
    )


def execute_case(
    case: KGCase, profile: ExtractionProfile, schema: KGSchema, adapter: ExtractorAdapter
) -> CaseExecution:
    """Preserve failures and successful partial blocks while assembling all product candidates."""
    started = perf_counter()
    text = decode_text(case.text.encode("utf-8"))
    source = _source(case, profile, text)
    raw_entities: list[ScoredEntity] = []
    relations: list[ScoredRelation] = []
    products: list[ProductExtraction] = []
    failures: list[KGEvalFailure] = []
    input_tokens = output_tokens = 0
    for block in chunk_text(text, profile.chunk_size, profile.chunk_overlap):
        try:
            result = checked_extract(adapter, block, schema)
        except KGExtractionError as error:
            failures.append(
                KGEvalFailure(
                    case_id=case.id, start=block.start, end=block.end, reason=error.reason
                )
            )
            continue
        input_tokens += result.input_tokens or 0
        output_tokens += result.output_tokens or 0
        raw_entities.extend(
            ScoredEntity(name=item.name, type=item.type) for item in result.output.entities
        )
        relations.extend(raw_relations(result.output, text))
        products.append(
            assemble_extraction(
                result.output,
                schema,
                source.model_copy(update={"block_start": block.start, "block_end": block.end}),
            )
        )
    raw = ScoredRecord(
        pid=case.id,
        entities=tuple(raw_entities),
        relations=tuple(relations),
        latency_s=perf_counter() - started,
        error=";".join(failure.reason for failure in failures) or None,
        failed_blocks=len(failures),
        usage=RecordedUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
        ),
    )
    entities, candidates = product_predictions(tuple(products), text)
    product = raw.model_copy(update={"entities": entities, "relations": candidates})
    return CaseExecution(
        raw=raw,
        product=product,
        blocked=blocked_relations(case.id, tuple(products)),
        failures=tuple(failures),
    )
