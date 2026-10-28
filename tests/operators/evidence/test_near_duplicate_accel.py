# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Independent brute-force checks exercise both native and reference comparison modes."""

from itertools import combinations
from random import Random

import datakeel_accel
import pytest

from datakeel.operators.evidence.near_duplicate_hashes import HashPair, compare_python


def _case(seed: int) -> tuple[list[int], int, int]:
    rng = Random(seed)  # noqa: S311  # Generated deterministic fixtures, not credentials.
    threshold = (0, 1, 2, 8, 16, 31, 63, 64)[seed % 8]
    hashes = [rng.getrandbits(64) for _ in range(seed % 24)]
    if seed % 5 == 0:
        hashes = [rng.getrandbits(64)] * (seed % 20)
    elif seed % 5 == 1:
        hashes = [value & ((1 << 60) - 1) for value in hashes]
    elif seed % 5 == 2:
        hashes = [(value & ~255) | 37 for value in hashes]
    if hashes:
        source = hashes[0]
        changed_bits = rng.sample(range(64), min(threshold, 8))
        mask = sum(1 << bit for bit in changed_bits)
        hashes.extend((source, source ^ mask, source ^ (1 << 63)))
    return hashes, threshold, seed % 65


def _brute(hashes: list[int], threshold: int) -> list[HashPair]:
    return [
        (left, right, distance)
        for (left, left_hash), (right, right_hash) in combinations(enumerate(hashes), 2)
        if (distance := (left_hash ^ right_hash).bit_count()) <= threshold
    ]


@pytest.mark.parametrize("seed", range(210))
def test_both_backends_match_brute_and_exact_contains_prefix(seed: int) -> None:
    """Verify 210 planted, uniform, repeated and adversarial inputs without tolerances."""
    hashes, threshold, prefix_bits = _case(seed)
    prefix = compare_python(hashes, threshold, prefix_bits, "prefix")
    exact = compare_python(hashes, threshold, prefix_bits, "exact")
    assert datakeel_accel.compare(hashes, threshold, prefix_bits, "prefix") == prefix
    assert datakeel_accel.compare(hashes, threshold, prefix_bits, "exact") == exact
    assert exact == _brute(hashes, threshold)
    assert set(prefix) <= set(exact)
    assert prefix == sorted(set(prefix))
    assert exact == sorted(set(exact))


@pytest.mark.parametrize("threshold", [0, 1, 8, 63, 64])
def test_exact_threshold_boundary_includes_only_direct_qualified_pairs(threshold: int) -> None:
    """Exercise equal-threshold and threshold-plus-one pairs at both 64-bit extremes."""
    hashes = [0, (1 << threshold) - 1, (1 << min(threshold + 1, 64)) - 1]
    assert datakeel_accel.compare(hashes, threshold, 4, "exact") == _brute(hashes, threshold)


def test_prefix_can_miss_cross_prefix_pair_that_exact_recovers() -> None:
    """Keep the documented default's recall limitation observable in both implementations."""
    hashes = [0, 1 << 63]
    assert compare_python(hashes, mode="prefix") == []
    assert datakeel_accel.compare(hashes, mode="prefix") == []
    assert compare_python(hashes, mode="exact") == [(0, 1, 1)]
    assert datakeel_accel.compare(hashes, mode="exact") == [(0, 1, 1)]
