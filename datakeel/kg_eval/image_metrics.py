# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Score image relation geometry and transcription fidelity without consulting model identities."""

from __future__ import annotations

import re
import unicodedata
from typing import TYPE_CHECKING

from datakeel.core.kg_eval_models import ImageGroupMetrics, ImageScoringView
from datakeel.kg_eval.alignment import match_entity
from datakeel.kg_eval.scoring import score_passages

if TYPE_CHECKING:
    from datakeel.core.kg_eval_models import ScoredRecord
    from datakeel.core.kg_image_eval import KGImageCase, KGImageSuite
    from datakeel.core.transcription_models import TranscriptionResult

type Box = tuple[float, float, float, float]
_IOU_THRESHOLD = 0.5


def region_iou(regions: tuple[Box, ...], gold: Box) -> float:
    """Compare the enclosing rectangle of every relation region with one gold rectangle."""
    if not regions:
        return 0.0
    left, bottom = min(box[0] for box in regions), min(box[1] for box in regions)
    right, top = max(box[2] for box in regions), max(box[3] for box in regions)
    intersection = max(0.0, min(right, gold[2]) - max(left, gold[0])) * max(
        0.0, min(top, gold[3]) - max(bottom, gold[1])
    )
    total = (
        (right - left) * (top - bottom) + (gold[2] - gold[0]) * (gold[3] - gold[1]) - intersection
    )
    return intersection / total if total else 0.0


def _boxes(record: ScoredRecord, case: KGImageCase) -> tuple[int, int]:
    matched: dict[tuple[str, str, str], list[tuple[Box, ...]]] = {}
    for relation in record.relations:
        head = match_entity(relation.head, case)
        tail = match_entity(relation.tail, case)
        label = re.sub(r"[\s\-]+", "_", relation.relation.strip().lower())
        if head is not None and tail is not None and head != tail:
            matched.setdefault((head, label, tail), []).append(relation.regions)
    gold = {relation.triple(): relation.boxes for relation in case.relations}
    present = set(gold) & set(matched)
    # Cases without gold geometry contribute no localisation denominator.
    evaluated = {key for key in present if gold[key]}
    hits = sum(
        any(
            region_iou(regions, box) >= _IOU_THRESHOLD
            for regions in matched[key]
            for box in gold[key]
        )
        for key in evaluated
    )
    return len(evaluated), hits


def _distance(first: str, second: str) -> int:
    previous = list(range(len(second) + 1))
    for index, char in enumerate(first, start=1):
        current = [index]
        for offset, other in enumerate(second, start=1):
            current.append(
                min(current[-1] + 1, previous[offset] + 1, previous[offset - 1] + (char != other))
            )
        previous = current
    return previous[-1]


def _text(value: str) -> str:
    return re.sub(r"[\s`*#>~\\]", "", unicodedata.normalize("NFKC", value))


def _quality(
    cases: tuple[KGImageCase, ...], transcripts: dict[str, TranscriptionResult]
) -> tuple[float | None, float | None, int]:
    edits = characters = identifiers = preserved = failures = 0
    for case in cases:
        result = transcripts.get(case.id)
        text = result.text if result else ""
        failures += int(result is None or bool(result.error or result.quality_issues))
        if case.group != "B":
            reference, observed = _text(case.text), _text(text)
            edits += _distance(reference, observed)
            characters += len(reference)
        observed_id = re.sub(
            r"\s+", "", unicodedata.normalize("NFKC", text).lower().replace("\\_", "_")
        )
        for entity in case.entities:
            if "_" in entity.name:
                identifiers += 1
                preserved += int(
                    re.sub(r"\s+", "", unicodedata.normalize("NFKC", entity.name).lower())
                    in observed_id
                )
    return (
        round(edits / characters, 4) if characters else None,
        round(preserved / identifiers, 3) if identifiers else None,
        failures,
    )


def image_scores(
    records: tuple[ScoredRecord, ...],
    suite: KGImageSuite,
    labels: set[str],
    transcripts: dict[str, TranscriptionResult],
) -> ImageScoringView:
    """Report clean, scanned and structural images independently, including language slices."""
    groups: list[ImageGroupMetrics] = []
    for name in (
        "A_clean",
        "A_scan",
        "B",
        "A_clean_zh",
        "A_clean_en",
        "A_scan_zh",
        "A_scan_en",
        "B_zh",
        "B_en",
    ):
        cases = tuple(
            case for case in suite.cases if name in {case.group, f"{case.group}_{case.lang}"}
        )
        gold = {case.id: case for case in cases}
        counts = [_boxes(record, gold[record.pid]) for record in records if record.pid in gold]
        total, hits = sum(row[0] for row in counts), sum(row[1] for row in counts)
        cer, identifiers, failures = _quality(cases, transcripts)
        groups.append(
            ImageGroupMetrics(
                name=name,
                metrics=score_passages(records, cases, labels),
                box_true_positives=total,
                box_hits=hits,
                box_hit_rate=round(hits / max(total, 1), 3),
                cer=cer,
                identifier_preservation=identifiers,
                transcription_failures=failures,
            )
        )
    return ImageScoringView(groups=tuple(groups))
