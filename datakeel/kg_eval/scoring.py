# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Reproduce the independent recording scorer and its language and grounding slices."""

from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING

from datakeel.core.kg_eval_models import PRF, KGMetrics, KGScoringView
from datakeel.kg_eval.alignment import verified
from datakeel.kg_eval.counts import entity_counts, relation_counts

if TYPE_CHECKING:
    from datakeel.core.kg_eval_models import KGCase, KGCaseSuite, ScoredRecord


def prf(tp: int, fp: int, fn: int) -> PRF:
    """Round each ratio exactly as the independent reference implementation does."""
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return PRF(p=round(precision, 3), r=round(recall, 3), f1=round(f1, 3), tp=tp, fp=fp, fn=fn)


def score_passages(
    records: tuple[ScoredRecord, ...], cases: tuple[KGCase, ...], labels: set[str]
) -> KGMetrics:
    """Aggregate exact counts; absent passages contribute relation false negatives only."""
    gold = {case.id: case for case in cases}
    counts: Counter[str] = Counter()
    latency = 0.0
    seen: set[str] = set()
    for record in records:
        if record.pid not in gold:
            continue
        seen.add(record.pid)
        case = gold[record.pid]
        latency += record.latency_s
        counts["errors"] += int(bool(record.error))
        counts["failed_blocks"] += record.failed_blocks or int(bool(record.error))
        counts.update(relation_counts(record, case, labels))
        counts.update(entity_counts(record, case))
        if record.usage is not None:
            counts["usage_records"] += 1
            counts["input_tokens"] += record.usage.input_tokens
            counts["output_tokens"] += record.usage.output_tokens
    missing = tuple(sorted(set(gold) - seen))
    counts["rfn"] += sum(len(gold[pid].relations) for pid in missing)
    return _metrics(counts, missing, len(seen), latency)


def _metrics(
    counts: Counter[str], missing: tuple[str, ...], seen: int, latency: float
) -> KGMetrics:
    denominator = max(counts["pred_rel"], 1)
    return KGMetrics(
        passages=seen,
        missing=missing,
        errors=counts["errors"],
        relation_strict=prf(counts["rtp"], counts["rfp"], counts["rfn"]),
        relation_pair=prf(counts["xtp"], counts["xfp"], counts["xfn"]),
        entity_typed=prf(counts["etp"], counts["efp"], counts["efn"]),
        entity_untyped=prf(counts["utp"], counts["ufp"], counts["ufn"]),
        trap_hits=counts["trap"],
        pred_relations=counts["pred_rel"],
        label_outside_schema=round(counts["bad_label"] / denominator, 3),
        endpoint_unmapped=counts["unmapped"],
        endpoint_in_text=round(counts["endpoints_located"] / max(counts["endpoints"], 1), 3),
        evidence_located=round(counts["ev_ok"] / denominator, 3),
        verified_ratio=round(counts["verified"] / denominator, 3),
        failed_blocks=counts["failed_blocks"],
        latency_total_s=round(latency, 1),
        latency_mean_s=round(latency / max(seen, 1), 2),
        input_tokens=counts["input_tokens"] if counts["usage_records"] else None,
        output_tokens=counts["output_tokens"] if counts["usage_records"] else None,
    )


def gate(records: tuple[ScoredRecord, ...], cases: tuple[KGCase, ...]) -> tuple[ScoredRecord, ...]:
    """Filter relations using the independent recorded gate or explicit product verification."""
    gold = {case.id: case for case in cases}
    return tuple(
        record.model_copy(
            update={
                "relations": tuple(
                    relation
                    for relation in record.relations
                    if verified(gold[record.pid].text, relation)
                )
            }
        )
        for record in records
        if record.pid in gold
    )


def score_views(
    records: tuple[ScoredRecord, ...], suite: KGCaseSuite, labels: set[str]
) -> KGScoringView:
    """Report unfiltered, language-specific, and verification-only metrics together."""
    return KGScoringView(
        all=score_passages(records, suite.cases, labels),
        zh=score_passages(
            records, tuple(case for case in suite.cases if case.lang == "zh"), labels
        ),
        en=score_passages(
            records, tuple(case for case in suite.cases if case.lang == "en"), labels
        ),
        verified=score_passages(gate(records, suite.cases), suite.cases, labels),
    )
