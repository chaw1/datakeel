# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Compare canonical direct dHash pairs without merging or transitive expansion."""

from collections import defaultdict
from pathlib import Path

from datakeel.core.evidence_drafts import ObservationDraft
from datakeel.core.evidence_models import ExtractorRef
from datakeel.core.models import FileItem
from datakeel.operators.base import Operator, OperatorResult, summarize
from datakeel.operators.evidence.common import EvidenceParams, anchor, publish, subject
from datakeel.operators.evidence.contracts import read_near_duplicate
from datakeel.operators.evidence.near_duplicate_hashes import (
    HashComparison,
    MatchMode,
    compare_hashes,
)

VERSION = "1.0"


class NearDuplicateParams(EvidenceParams):
    """Allow an explicit matching mode while retaining the versioned contract default."""

    mode: MatchMode | None = None


def _compare_files(
    files: list[FileItem], mode: MatchMode | None
) -> tuple[list[FileItem], HashComparison, MatchMode]:
    contract = read_near_duplicate()
    selected_mode = mode if mode is not None else contract.mode
    ordered = sorted(files, key=lambda file: (subject(file).asset_id, file.id))
    selected = [file for file in ordered if isinstance(file.metadata.get("image_phash"), str)]
    hashes = [int(str(file.metadata["image_phash"]), 16) for file in selected]
    comparison = compare_hashes(
        hashes, contract.hamming_threshold, contract.prefix_bits, selected_mode
    )
    return selected, comparison, selected_mode


def duplicate_pairs(
    files: list[FileItem], mode: MatchMode | None = None
) -> list[tuple[FileItem, FileItem, int]]:
    """Return individually measured pairs ordered by canonical subject identities."""
    selected, comparison, _mode = _compare_files(files, mode)
    return [
        (selected[left], selected[right], distance) for left, right, distance in comparison.pairs
    ]


def execute(
    files: list[FileItem], _output_dir: Path, params: NearDuplicateParams
) -> OperatorResult:
    """Publish direct-pair evidence and record the measured backend even for empty results."""
    selected, comparison, mode = _compare_files(files, params.mode)
    drafts: dict[str, list[ObservationDraft]] = defaultdict(list)
    for left_index, right_index, distance in comparison.pairs:
        left, right = selected[left_index], selected[right_index]
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
    output = [
        publish(
            file,
            drafts[file.id],
            near_duplicate_implementation=comparison.implementation,
            near_duplicate_implementation_version=comparison.implementation_version,
            near_duplicate_mode=mode,
        )
        for file in files
    ]
    result = summarize(files, output)
    return result.model_copy(
        update={
            "quality": {
                **result.quality,
                "implementation": comparison.implementation,
                "implementation_version": comparison.implementation_version,
                "match_mode": mode,
            }
        }
    )


OPERATOR = Operator("evidence.near_duplicate", "image", "evidence", NearDuplicateParams, execute)
