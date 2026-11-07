# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Offline E5 numerical, metric and real-campaign assertion anchors for both CI stacks."""

from scripts.mutation_models import Mutation

_NUMERIC = "tests/evaluation/test_we_e5_numeric.py::"
_CAMPAIGN = "tests/evaluation/test_we_e5_campaign.py::"


def _numeric(name: str, before: str, after: str, case: str) -> Mutation:
    return Mutation(
        name="we-e5-" + name,
        path="scripts/we_e5/numeric.py",
        before=before,
        after=after,
        case=_NUMERIC + case,
        runner="pytest",
        source_root="repository",
    )


WE_E5_MUTATIONS = (
    Mutation(
        name="we-e5-wheel-payload",
        path="scripts/we_e5/dependencies.py",
        before='if any("faiss" in name.lower() or name.startswith("scripts/") for name in names):',
        after="if False:",
        case="tests/evaluation/test_we_e5_dependencies.py::test_product_wheel_with_faiss_payload_is_rejected",
        runner="pytest",
        source_root="repository",
    ),
    Mutation(
        name="we-e5-wheel-requirement",
        path="scripts/we_e5/dependencies.py",
        before='if "faiss" in str(message.get_all("Requires-Dist", ())).lower():',
        after="if False:",
        case="tests/evaluation/test_we_e5_dependencies.py::test_product_wheel_with_faiss_requirement_is_rejected",
        runner="pytest",
        source_root="repository",
    ),
    _numeric(
        "gap-nearest-tie",
        "best = min(refs, key=",
        "best = max(refs, key=",
        "test_handwritten_oracle_checks_production_and_faiss_all_metrics",
    ),
    Mutation(
        name="we-e5-float-disagreement",
        path="scripts/we_e5/report.py",
        before="if getattr(product, key) != getattr(candidate, key)",
        after="if False",
        case=_NUMERIC + "test_float_error_and_threshold_disagreement_are_retained",
        runner="pytest",
        source_root="repository",
    ),
    _numeric(
        "index-normalization",
        "    index.add(matrix)",
        "    index.add(matrix * 2)",
        "test_both_index_and_queries_use_same_normalized_f32_prefix",
    ),
    _numeric(
        "query-normalization",
        "index.search(matrix, len(samples))",
        "index.search(matrix * 2, len(samples))",
        "test_both_index_and_queries_use_same_normalized_f32_prefix",
    ),
    _numeric(
        "shared-normalization",
        "matrix / norms[:, None]",
        "matrix",
        "test_both_index_and_queries_use_same_normalized_f32_prefix",
    ),
    _numeric(
        "duplicate-inclusive",
        "if scores[positions[left]][positions[right]] >= case.threshold",
        "if scores[positions[left]][positions[right]] > case.threshold",
        "test_inclusive_threshold_and_dbscan_distance_strict_gap",
    ),
    _numeric(
        "dbscan-inclusive",
        "1.0 - similarity <= case.eps",
        "1.0 - similarity < case.eps",
        "test_inclusive_threshold_and_dbscan_distance_strict_gap",
    ),
    _numeric(
        "insufficient-published-noise",
        "if len(ids) < min_samples:",
        "if False:",
        "test_dbscan_self_and_insufficient_are_explicit",
    ),
    _numeric(
        "greedy-seen",
        "kept, key=lambda peer:",
        "[peer for peer in targets if peer < identity], key=lambda peer:",
        "test_greedy_seen_set_does_not_remove_transitive_chain",
    ),
    _numeric(
        "greedy-tie",
        "kept, key=lambda peer: (-scores[positions[identity]][positions[peer]], peer)",
        (
            "kept, key=lambda peer: (-scores[positions[identity]][positions[peer]], "
            "tuple(-ord(c) for c in peer))"
        ),
        "test_greedy_exact_score_ties_choose_smallest_kept_asset_id",
    ),
    _numeric(
        "gap-strict",
        "if scores[positions[identity]][positions[best]] < case.gap_threshold:",
        "if scores[positions[identity]][positions[best]] <= case.gap_threshold:",
        "test_inclusive_threshold_and_dbscan_distance_strict_gap",
    ),
    Mutation(
        name="we-e5-gold-unavailable",
        path="scripts/we_e5/metrics.py",
        before="        gap=gap,",
        after="        gap=score(set(), set()),",
        case=_NUMERIC + "test_absent_gold_metrics_are_not_available",
        runner="pytest",
        source_root="repository",
    ),
    Mutation(
        name="we-e5-ari-chance",
        path="scripts/we_e5/metrics.py",
        before="expected = a * b / comb(count, 2)",
        after="expected = 0.0",
        case=_NUMERIC + "test_metric_formulas_include_chance_adjustment_and_arithmetic_nmi",
        runner="pytest",
        source_root="repository",
    ),
    Mutation(
        name="we-e5-hot-zero",
        path="scripts/we_e5/campaign.py",
        before="and hot.dispatch_count == 0",
        after="and hot.dispatch_count >= 0",
        case=_CAMPAIGN + "test_hot_evidence_with_nonzero_calls_is_rejected",
        runner="pytest",
        source_root="repository",
    ),
    Mutation(
        name="we-e5-incremental-peer",
        path="scripts/we_e5/campaign.py",
        before='and incremental.attempted_asset_ids == ("target-00000",)',
        after="and True",
        case=_CAMPAIGN + "test_incremental_evidence_wrong_peer_is_rejected",
        runner="pytest",
        source_root="repository",
    ),
    Mutation(
        name="we-e5-cold-empty",
        path="scripts/we_e5/campaign.py",
        before="cold.cache_before.embeddings == ()",
        after="True",
        case=_CAMPAIGN + "test_cold_evidence_with_existing_cache_is_rejected",
        runner="pytest",
        source_root="repository",
    ),
    Mutation(
        name="we-e5-cold-globals-empty",
        path="scripts/we_e5/campaign.py",
        before="cold.cache_before.globals == ()",
        after="True",
        case=_CAMPAIGN + "test_cold_evidence_with_existing_globals_is_rejected",
        runner="pytest",
        source_root="repository",
    ),
    Mutation(
        name="we-e5-rss-unit",
        path="scripts/we_e5/worker.py",
        before="return raw * 1024",
        after="return raw",
        case=_NUMERIC + "test_rss_platform_units_are_explicit",
        runner="pytest",
        source_root="repository",
    ),
)
