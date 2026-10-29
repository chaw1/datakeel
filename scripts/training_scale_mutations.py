# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Keep bounded training candidate retrieval identical while reusing immutable rows."""

from scripts.mutation_models import Mutation

_CANDIDATE_CASE = (
    "tests/llm_data/test_index_candidates.py::"
    "test_candidate_queries_preserve_each_band_limit_deduplication_and_record_order"
)

TRAINING_SCALE_MUTATIONS = (
    Mutation(
        name="training-candidate-band-recency",
        path="llm_data/index.py",
        before="ORDER BY record_id DESC LIMIT ?",
        after="ORDER BY record_id ASC LIMIT ?",
        case=_CANDIDATE_CASE,
        runner="pytest",
    ),
    Mutation(
        name="training-candidate-representative-order",
        path="llm_data/index.py",
        before="for identity in sorted(rows)]",
        after="for identity in sorted(rows, reverse=True)]",
        case=_CANDIDATE_CASE,
        runner="pytest",
    ),
    Mutation(
        name="training-candidate-cache-refresh",
        path="llm_data/index.py",
        before="self._bands[band] = (identity, *previous[: _CANDIDATES_PER_BAND - 1])",
        after="self._bands[band] = previous",
        case=(
            "tests/llm_data/test_index_candidates.py::"
            "test_candidate_cache_refreshes_recent_ids_after_new_records"
        ),
        runner="pytest",
    ),
    Mutation(
        name="training-candidate-row-size-bound",
        path="llm_data/index.py",
        before="if sum(len(row[index]) for index in (0, 1, 3, 4)) > _MAX_CACHED_ROW_CHARACTERS:",
        after="if False:",
        case=(
            "tests/llm_data/test_index_candidates.py::"
            "test_candidate_cache_bypasses_oversized_rows_and_band_keys"
        ),
        runner="pytest",
    ),
    Mutation(
        name="training-candidate-row-entry-bound",
        path="llm_data/index.py",
        before="if len(self._rows) > _MAX_CACHED_ROWS:",
        after="if False:",
        case=(
            "tests/llm_data/test_index_candidates.py::"
            "test_candidate_caches_evict_entries_and_preserve_disk_results"
        ),
        runner="pytest",
    ),
    Mutation(
        name="training-candidate-band-entry-bound",
        path="llm_data/index.py",
        before="if len(self._bands) > _MAX_CACHED_BANDS:",
        after="if False:",
        case=(
            "tests/llm_data/test_index_candidates.py::"
            "test_candidate_caches_evict_entries_and_preserve_disk_results"
        ),
        runner="pytest",
    ),
)
