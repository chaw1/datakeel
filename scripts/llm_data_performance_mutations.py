# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Keep performance shortcuts conservative and similarity caches bounded."""

from scripts.mutation_models import Mutation

LLM_DATA_PERFORMANCE_MUTATIONS = (
    Mutation(
        name="training-native-similarity-cache-entry-bound",
        path="llm_data/acceleration.py",
        before="    cached = lru_cache(maxsize=_CACHED_SHINGLES)(shingles)",
        after="    cached = lru_cache(maxsize=None)(shingles)",
        case=(
            "tests/llm_data/test_acceleration.py::"
            "test_native_similarity_cache_when_entries_or_text_grow_stays_bounded"
        ),
        runner="pytest",
    ),
    Mutation(
        name="training-native-similarity-cache-text-bound",
        path="llm_data/acceleration.py",
        before="        return cached(text) if len(text) <= _MAX_CACHED_TEXT else shingles(text)",
        after="        return cached(text)",
        case=(
            "tests/llm_data/test_acceleration.py::"
            "test_native_similarity_cache_when_entries_or_text_grow_stays_bounded"
        ),
        runner="pytest",
    ),
    Mutation(
        name="pii-conservative-label-prefilter",
        path="core/pii_credentials.py",
        before="    if patterns.LABEL_HINT.search(text) is None:",
        after="    if True:",
        case=(
            "tests/core/test_pii_credential_guards.py::"
            "test_privacy_prefilters_preserve_minimum_numeric_and_secret_shapes"
        ),
        runner="pytest",
    ),
    Mutation(
        name="training-repetition-overlapping-denominator",
        path="llm_data/checks.py",
        before="    return 1 - len(grams) / (len(tokens) - 2)",
        after="    return 1 - len(grams) / len(tokens)",
        case=(
            "tests/llm_data/test_similarity_cache.py::"
            "test_repetition_fraction_counts_overlapping_trigrams_in_both_scripts"
        ),
        runner="pytest",
    ),
    Mutation(
        name="training-similarity-cache-size-bound",
        path="llm_data/similarity.py",
        before="    if len(text) <= _MAX_CACHED_TEXT:",
        after="    if True:",
        case=(
            "tests/llm_data/test_similarity_cache.py::"
            "test_similarity_cache_preserves_measurements_and_bypasses_oversized_text"
        ),
        runner="pytest",
    ),
    Mutation(
        name="pii-conservative-numeric-prefilter",
        path="core/pii.py",
        before="    if patterns.NUMBER_RUN.search(text) is None:",
        after="    if True:",
        case=(
            "tests/core/test_pii_credential_guards.py::"
            "test_privacy_prefilters_preserve_minimum_numeric_and_secret_shapes"
        ),
        runner="pytest",
    ),
)
