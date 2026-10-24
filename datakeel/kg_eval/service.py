# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Evaluate injected extractors using both independent and real production-path scoring."""

from __future__ import annotations

from decimal import Decimal
from time import perf_counter
from typing import TYPE_CHECKING

from datakeel.core.kg_eval_models import KGEvalReport
from datakeel.kg.loader import contracts_path
from datakeel.kg_eval.execution import execute_case
from datakeel.kg_eval.loader import load_cases, load_recording, original_records
from datakeel.kg_eval.scoring import score_views

if TYPE_CHECKING:
    from pathlib import Path

    from datakeel.core.kg_contracts import ExtractionProfile, KGSchema
    from datakeel.core.kg_eval_models import KGCaseSuite, ScoredRecord
    from datakeel.kg.extractors import ExtractorAdapter


def _recording_view(
    profile: ExtractionProfile, suite: KGCaseSuite, observed: tuple[ScoredRecord, ...]
) -> tuple[ScoredRecord, ...]:
    if profile.extractor != "replay" or not profile.recording:
        return observed
    archive = load_recording(contracts_path() / profile.recording)
    originals = {item.pid: item for item in original_records(archive, suite) if item.error is None}
    return tuple(originals.get(item.pid, item) for item in observed)


def evaluate_kg(
    profile: ExtractionProfile,
    schema: KGSchema,
    extractor: ExtractorAdapter,
    cases_path: Path | None = None,
) -> KGEvalReport:
    """Run generic cases through chunking, extraction, schema checks, anchors and triple merging."""
    started = perf_counter()
    suite, digest = load_cases(schema, cases_path)
    executions = tuple(execute_case(case, profile, schema, extractor) for case in suite.cases)
    observed = tuple(execution.raw for execution in executions)
    original = _recording_view(profile, suite, observed)
    products = tuple(execution.product for execution in executions)
    labels = {relation.name for relation in schema.relations}
    offline = profile.extractor in {"fake", "replay", "gliner2"}
    return KGEvalReport(
        profile=profile.id,
        model=profile.model,
        suite_digest=digest,
        recording=score_views(original, suite, labels),
        product=score_views(products, suite, labels),
        blocked_relations=tuple(item for execution in executions for item in execution.blocked),
        elapsed_seconds=perf_counter() - started,
        input_tokens=0
        if offline
        else sum(item.usage.input_tokens for item in observed if item.usage),
        output_tokens=0
        if offline
        else sum(item.usage.output_tokens for item in observed if item.usage),
        cost_usd=Decimal(0) if offline else None,
    )
