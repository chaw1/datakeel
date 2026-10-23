# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Compare direct blocked dHash pairs without merging or transitive expansion."""

from collections import defaultdict
from itertools import combinations
from pathlib import Path

from datakeel.core.evidence_drafts import ObservationDraft
from datakeel.core.evidence_models import ExtractorRef
from datakeel.core.models import FileItem
from datakeel.operators.base import Operator, OperatorResult, summarize
from datakeel.operators.evidence.common import EvidenceParams, anchor, publish, subject
from datakeel.operators.evidence.contracts import read_near_duplicate

VERSION = "1.0"


def _hash(file: FileItem) -> int | None:
    value = file.metadata.get("image_phash")
    return int(value, 16) if isinstance(value, str) else None


def duplicate_pairs(files: list[FileItem]) -> list[tuple[FileItem, FileItem, int]]:
    """Return only individually measured, canonical pairs inside matching prefixes."""
    contract = read_near_duplicate()
    buckets: dict[int, list[tuple[FileItem, int]]] = defaultdict(list)
    for file in sorted(files, key=lambda item: subject(item).asset_id):
        value = _hash(file)
        if value is not None:
            buckets[value >> (contract.bits - contract.prefix_bits)].append((file, value))
    pairs: list[tuple[FileItem, FileItem, int]] = []
    for bucket in buckets.values():
        for (left, left_hash), (right, right_hash) in combinations(bucket, 2):
            distance = (left_hash ^ right_hash).bit_count()
            if distance <= contract.hamming_threshold:
                pairs.append((left, right, distance))
    return pairs


def execute(files: list[FileItem], _output_dir: Path, params: EvidenceParams) -> OperatorResult:
    """Publish one assertion draft per canonical pair, attached to its smaller subject."""
    drafts: dict[str, list[ObservationDraft]] = defaultdict(list)
    for left, right, distance in duplicate_pairs(files):
        left_ref, right_ref = subject(left), subject(right)
        drafts[left.id].append(
            ObservationDraft(
                subject=left_ref,
                predicate="near_duplicate_of",
                object=right_ref,
                anchors=(anchor(left, left_ref), anchor(right, right_ref)),
                extractor=ExtractorRef(
                    id="evidence.near_duplicate", version=params.extractor_version
                ),
                distance=distance,
                reason=f"Direct 64-bit dHash Hamming distance {distance} within contract threshold",
            )
        )
    return summarize(files, [publish(file, drafts[file.id]) for file in files])


OPERATOR = Operator("evidence.near_duplicate", "image", "evidence", EvidenceParams, execute)
