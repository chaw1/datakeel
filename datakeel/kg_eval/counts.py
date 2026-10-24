# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Count benchmark triples and entities without product filtering or identity rules."""

from __future__ import annotations

import re
from collections import Counter
from typing import TYPE_CHECKING

from datakeel.core.kg_eval_models import ScoredEntity
from datakeel.kg_eval.alignment import evidence_located, located, match_entity, norm, verified

if TYPE_CHECKING:
    from datakeel.core.kg_eval_models import KGCase, ScoredRecord


def relation_counts(record: ScoredRecord, case: KGCase, labels: set[str]) -> Counter[str]:
    """Score unique oriented triples and unordered endpoint pairs, retaining invalid outputs."""
    counts: Counter[str] = Counter()
    strict: set[tuple[str, str, str]] = set()
    pairs: set[frozenset[str]] = set()
    unmapped: set[tuple[str, str, str]] = set()
    for relation in record.relations:
        counts["pred_rel"] += 1
        label = re.sub(r"[\s\-]+", "_", relation.relation.strip().lower())
        counts["bad_label"] += int(label not in labels)
        counts["endpoints"] += 2
        counts["endpoints_located"] += sum(
            int(located(case.text, name)) for name in (relation.head, relation.tail)
        )
        counts["ev_ok"] += int(evidence_located(case.text, relation))
        counts["verified"] += int(verified(case.text, relation))
        head, tail = match_entity(relation.head, case), match_entity(relation.tail, case)
        if head is None or tail is None or head == tail:
            unmapped.add((norm(relation.head), label, norm(relation.tail)))
            continue
        strict.add((head, label, tail))
        pairs.add(frozenset((head, tail)))
    counts.update(_triple_counts(strict, case))
    counts.update(_pair_counts(pairs, case))
    counts["unmapped"] = len(unmapped)
    counts["rfp"] += len(unmapped)
    counts["xfp"] += len(unmapped)
    return counts


def _triple_counts(predicted: set[tuple[str, str, str]], case: KGCase) -> Counter[str]:
    gold = {relation.triple() for relation in case.relations}
    optional = {relation.triple() for relation in case.optional}
    traps = {relation.triple() for relation in case.traps}
    return Counter(
        rtp=len(predicted & gold),
        rfp=len(predicted - gold - optional),
        rfn=len(gold - predicted),
        trap=len((predicted - gold - optional) & traps),
    )


def _pair_counts(predicted: set[frozenset[str]], case: KGCase) -> Counter[str]:
    gold = {frozenset((relation.head, relation.tail)) for relation in case.relations}
    optional = {frozenset((relation.head, relation.tail)) for relation in case.optional}
    return Counter(
        xtp=len(predicted & gold), xfp=len(predicted - gold - optional), xfn=len(gold - predicted)
    )


def entity_counts(record: ScoredRecord, case: KGCase) -> Counter[str]:
    """Match entities once per canonical name/type and preserve raw unmatched false positives."""
    gold_typed = {(entity.name, entity.type) for entity in case.entities}
    gold_names = {entity.name for entity in case.entities}
    entities = record.entities or tuple(
        ScoredEntity(name=name)
        for relation in record.relations
        for name in (relation.head, relation.tail)
    )
    typed: set[tuple[str, str | None]] = set()
    names: set[str] = set()
    unmatched: set[str] = set()
    for entity in entities:
        matched = match_entity(entity.name, case, entity.type)
        if matched is None:
            unmatched.add(norm(entity.name))
            continue
        names.add(matched)
        typed.add((matched, entity.type))
    return Counter(
        etp=len(typed & gold_typed),
        efp=len(typed - gold_typed) + len(unmatched),
        efn=len(gold_typed - typed),
        utp=len(names & gold_names),
        ufp=len(unmatched),
        ufn=len(gold_names - names),
    )
