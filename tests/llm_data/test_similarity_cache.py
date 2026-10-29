# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Bound reusable similarity features without changing direct pair measurements."""

from datakeel.llm_data.checks import repetition_ratio
from datakeel.llm_data.similarity import _cached_shingles, similarity


def test_similarity_cache_preserves_measurements_and_bypasses_oversized_text() -> None:
    """Cache small Unicode features, evict old entries, and never retain oversized lines."""
    _cached_shingles.cache_clear()
    left = "河流观察记录说明不同树木在山谷里的生长情况。" * 20
    right = left.replace("树木", "植物")
    first = similarity(left, right)
    assert 0 < first < 1
    assert similarity(left, right) == first
    assert _cached_shingles.cache_info().hits >= 2
    for number in range(300):
        similarity(f"{number} unique observations " * 20, right)
    assert _cached_shingles.cache_info().currsize <= 256
    before = _cached_shingles.cache_info()
    large_left = "河流观察记录树木山谷" * 600
    large_right = large_left.replace("树木", "植物")
    score = similarity(large_left, large_right)
    assert 0 < score < 1
    assert _cached_shingles.cache_info() == before
    _cached_shingles.cache_clear()


def test_repetition_fraction_counts_overlapping_trigrams_in_both_scripts() -> None:
    """Twelve tokens have ten overlapping trigrams, including the two trailing starts."""
    assert repetition_ratio("red green blue " * 4) == 0.7
    assert repetition_ratio("山河林" * 4) == 0.7
    assert repetition_ratio("red " * 11) == 0
