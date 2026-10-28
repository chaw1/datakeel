# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Deterministic iterative stratification with indivisible connected sample groups."""

import hashlib
import math
from collections import Counter, defaultdict

from datakeel.core.errors import ValidationError
from datakeel.core.training_models import (
    LabelCount,
    SplitDistribution,
    SplitMember,
    SplitName,
    SplitRequest,
    TrainingSample,
)
from datakeel.training.leakage import signal_pairs

SPLITS: tuple[SplitName, ...] = ("train", "val", "test")


def _groups(samples: tuple[TrainingSample, ...], request: SplitRequest) -> list[list[int]]:
    parents = list(range(len(samples)))

    def root(index: int) -> int:
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    for left, right, kind, _, _ in signal_pairs(samples, request):
        if kind == "group" or request.avoid_leakage:
            left_root, right_root = root(left), root(right)
            parents[max(left_root, right_root)] = min(left_root, right_root)
    grouped: dict[int, list[int]] = defaultdict(list)
    for index in range(len(samples)):
        grouped[root(index)].append(index)
    return list(grouped.values())


def _rank(seed: int, identity: str) -> str:
    return hashlib.sha256(f"{seed}:{identity}".encode()).hexdigest()


def _capacities(count: int, request: SplitRequest) -> dict[SplitName, int]:
    ratios = request.ratios
    raw: dict[SplitName, float] = {
        "train": count * ratios.train,
        "val": count * ratios.val,
        "test": count * ratios.test,
    }
    result: dict[SplitName, int] = {split: math.floor(value) for split, value in raw.items()}
    remainder = count - sum(result.values())
    priority = sorted(
        SPLITS, key=lambda split: (-(raw[split] - result[split]), SPLITS.index(split))
    )
    for split in priority[:remainder]:
        result[split] += 1
    return result


def _single_labels(
    samples: tuple[TrainingSample, ...], request: SplitRequest
) -> dict[int, SplitName]:
    strata: dict[tuple[str, ...], list[int]] = defaultdict(list)
    for index, sample in enumerate(samples):
        strata[sample.labels if request.stratify else ()].append(index)
    result: dict[int, SplitName] = {}
    for _label, indices in sorted(strata.items()):
        ordered = sorted(indices, key=lambda index: _rank(request.seed, samples[index].file.id))
        capacities = _capacities(len(indices), request)
        offset = 0
        for split in SPLITS:
            for index in ordered[offset : offset + capacities[split]]:
                result[index] = split
            offset += capacities[split]
    return result


def _iterative(
    samples: tuple[TrainingSample, ...], groups: list[list[int]], request: SplitRequest
) -> dict[int, SplitName]:
    labels = [
        Counter(label for index in group for label in samples[index].labels) for group in groups
    ]
    totals = sum(labels, Counter[str]())
    desired = {
        split: {label: count * getattr(request.ratios, split) for label, count in totals.items()}
        for split in SPLITS
    }
    capacity = _capacities(len(samples), request)
    remaining = set(range(len(groups)))
    result: dict[int, SplitName] = {}
    while remaining:
        counts = sum((labels[index] for index in remaining), Counter[str]())
        rare = (
            min(counts, key=lambda label: (counts[label], label))
            if counts and request.stratify
            else None
        )
        candidates = [index for index in remaining if rare is None or labels[index][rare]]
        candidates.sort(
            key=lambda index: (
                -len(groups[index]),
                _rank(request.seed, samples[groups[index][0]].file.id),
            )
        )
        for index in candidates:
            active: list[SplitName] = [
                split for split in SPLITS if getattr(request.ratios, split) > 0
            ]
            selected = max(
                active,
                key=lambda split: (
                    desired[split].get(rare or "", 0),
                    capacity[split],
                    -SPLITS.index(split),
                ),
            )
            for member in groups[index]:
                result[member] = selected
            capacity[selected] -= len(groups[index])
            for label, count in labels[index].items():
                desired[selected][label] -= count
            remaining.remove(index)
    return result


def _directory(samples: tuple[TrainingSample, ...]) -> dict[int, SplitName]:
    result: dict[int, SplitName] = {}
    for index, sample in enumerate(samples):
        split = sample.file.metadata.get("split")
        if split not in SPLITS:
            message = "Every directory split sample needs train, val or test split metadata"
            raise ValidationError(message)
        result[index] = next(name for name in SPLITS if name == split)
    return result


def split_samples(
    samples: tuple[TrainingSample, ...], request: SplitRequest
) -> tuple[SplitMember, ...]:
    """Assign all samples once; atomic groups take priority over unattainable ratio targets."""
    ordered = tuple(sorted(samples, key=lambda sample: sample.file.id))
    if len({sample.file.id for sample in ordered}) != len(ordered):
        message = "Training samples must have distinct identities"
        raise ValidationError(message)
    if request.source == "directory":
        assignments = _directory(ordered)
    else:
        groups = _groups(ordered, request)
        independent = all(len(group) == 1 for group in groups)
        simple = all(len(sample.labels) <= 1 for sample in ordered)
        assignments = (
            _single_labels(ordered, request)
            if independent and simple
            else _iterative(ordered, groups, request)
        )
    return tuple(
        SplitMember(
            sample_id=sample.file.id,
            split=assignments[index],
            labels=sample.labels,
            annotations=sample.annotations,
            sha256=sample.file.sha256,
        )
        for index, sample in enumerate(ordered)
    )


def distributions(members: tuple[SplitMember, ...]) -> tuple[SplitDistribution, ...]:
    """Include all categories and zero counts so every partition is directly comparable."""
    categories = sorted({label for member in members for label in member.labels})
    result: list[SplitDistribution] = []
    for split in SPLITS:
        selected = [member for member in members if member.split == split]
        counts = Counter(label for member in selected for label in set(member.labels))
        result.append(
            SplitDistribution(
                split=split,
                count=len(selected),
                labels=tuple(LabelCount(label=label, count=counts[label]) for label in categories),
            )
        )
    return tuple(result)
