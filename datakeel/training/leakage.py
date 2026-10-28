# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Find exact direct duplicate and group matches through shared 64-bit comparison."""

from collections import defaultdict
from collections.abc import Iterator
from itertools import combinations

from datakeel.core.training_models import (
    LeakageKind,
    LeakagePair,
    LeakageReport,
    SplitName,
    SplitRequest,
    SplitSet,
    TrainingSample,
)
from datakeel.operators.evidence.near_duplicate_hashes import compare_hashes

type SignalPair = tuple[int, int, LeakageKind, int, str]
UNIFORM_COLOR_THRESHOLD = 12


def _image_confirmation(left: TrainingSample, right: TrainingSample) -> bool:
    if not left.image_uniform and not right.image_uniform:
        return True
    if not left.image_uniform or not right.image_uniform:
        return False
    if left.image_color is None or right.image_color is None:
        return False
    return all(
        abs(a - b) <= UNIFORM_COLOR_THRESHOLD
        for a, b in zip(left.image_color, right.image_color, strict=True)
    )


def _equal_pairs(samples: tuple[TrainingSample, ...], field: str) -> Iterator[SignalPair]:
    buckets: dict[str, list[int]] = defaultdict(list)
    for index, sample in enumerate(samples):
        value = sample.file.sha256 if field == "exact" else sample.group
        if value:
            buckets[value].append(index)
    kind: LeakageKind = "exact" if field == "exact" else "group"
    for indices in buckets.values():
        for left, right in combinations(indices, 2):
            yield (
                left,
                right,
                kind,
                0,
                "SHA-256 content equality" if field == "exact" else "Group key equality",
            )


def _hash_pairs(
    samples: tuple[TrainingSample, ...], kind: LeakageKind, threshold: int
) -> Iterator[SignalPair]:
    values = [
        (index, value)
        for index, sample in enumerate(samples)
        if (value := sample.image_hash if kind == "image" else sample.text_hash) is not None
    ]
    comparison = compare_hashes([value for _, value in values], threshold, mode="exact")
    for left, right, distance in comparison.pairs:
        if kind == "image" and not _image_confirmation(
            samples[values[left][0]], samples[values[right][0]]
        ):
            continue
        yield (
            values[left][0],
            values[right][0],
            kind,
            distance,
            f"64-bit {'dHash' if kind == 'image' else 'simhash'} Hamming distance <= {threshold}"
            + (
                f"; low-texture RGB channel difference <= {UNIFORM_COLOR_THRESHOLD}"
                if kind == "image" and samples[values[left][0]].image_uniform
                else ""
            ),
        )


def signal_pairs(
    samples: tuple[TrainingSample, ...], request: SplitRequest
) -> Iterator[SignalPair]:
    """Yield all direct measured edges, using lossless comparison rather than prefix blocking."""
    yield from _equal_pairs(samples, "exact")
    yield from _equal_pairs(samples, "group")
    yield from _hash_pairs(samples, "image", request.image_threshold)
    yield from _hash_pairs(samples, "text", request.text_threshold)


def leakage_report(samples: tuple[TrainingSample, ...], split: SplitSet) -> LeakageReport:
    """Measure each of the four leakage signals and retain only cross-partition pairs."""
    assignments: dict[str, SplitName] = {member.sample_id: member.split for member in split.members}
    pairs: list[LeakagePair] = []
    for left, right, kind, distance, detail in signal_pairs(samples, split.request):
        left_id, right_id = samples[left].file.id, samples[right].file.id
        if assignments[left_id] != assignments[right_id]:
            pairs.append(
                LeakagePair(
                    kind=kind,
                    left_id=left_id,
                    right_id=right_id,
                    left_split=assignments[left_id],
                    right_split=assignments[right_id],
                    distance=distance,
                    detail=detail,
                )
            )
    return LeakageReport(
        split_set_id=split.id,
        dataset_id=split.dataset_id,
        version_id=split.version_id,
        sample_count=len(samples),
        pairs=tuple(sorted(pairs, key=lambda pair: (pair.kind, pair.left_id, pair.right_id))),
    )
