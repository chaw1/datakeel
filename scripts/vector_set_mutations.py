# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Named assertion-only anchors for deterministic set evidence and reference closure safety."""

from scripts.mutation_models import Mutation

VECTOR_SET_MUTATIONS = (
    Mutation(
        name="vector-dbscan-inclusive",
        path="evidence/vector_sets.py",
        before="1.0 - cosine(left, valid[j]) <= eps",
        after="1.0 - cosine(left, valid[j]) < eps",
        case="tests/evidence/test_vector_sets.py::test_dbscan_distance_boundary_and_border_first_cluster",
        runner="pytest",
    ),
    Mutation(
        name="vector-dbscan-self",
        path="evidence/vector_sets.py",
        before="neighbors = [{i} for i in range(len(valid))]",
        after="neighbors = [set() for i in range(len(valid))]",
        case="tests/evidence/test_vector_sets.py::test_dbscan_core_border_noise_stable_permutation",
        runner="pytest",
    ),
    Mutation(
        name="vector-dbscan-first-border",
        path="evidence/vector_sets.py",
        before="if labels[peer] == -1:",
        after="if labels[peer] == -1 or not core[peer]:",
        case="tests/evidence/test_vector_sets.py::test_dbscan_distance_boundary_and_border_first_cluster",
        runner="pytest",
    ),
    Mutation(
        name="vector-gap-nearest-tie",
        path="evidence/vector_sets.py",
        before="(-cosine(sample, ref), ref.subject.asset_id)",
        after="(-cosine(sample, ref), tuple(-ord(c) for c in ref.subject.asset_id))",
        case="tests/evidence/test_vector_sets.py::test_coverage_union_difference_tie_and_relative_threshold",
        runner="pytest",
    ),
    Mutation(
        name="vector-gap-reference-closure",
        path="core/vector_assertion_rules.py",
        before="refs.extend(m.subject for m in assertion.measurement.references)",
        after="refs.append(assertion.measurement.nearest)",
        case="tests/evidence/test_vector_set_authorization.py::test_gap_non_nearest_reference_authorizes_prepare_read_review_and_revoke",
        runner="pytest",
    ),
    Mutation(
        name="vector-gap-reference-invalidation",
        path="storage/vector_current.py",
        before="return current.members == assertion.measurement.references",
        after="return True",
        case="tests/evidence/test_vector_set_authorization.py::test_gap_reference_change_invalidates_query_and_review_including_non_nearest",
        runner="pytest",
    ),
    Mutation(
        name="vector-set-late-publication",
        path="persistence/task_vector.py",
        before="if error:\n        return ()",
        after="if error:\n        return evidence",
        case="tests/evidence/test_vector_set_capacity.py::test_set_error_completion_discards_successful_pending",
        runner="pytest",
    ),
    Mutation(
        name="vector-set-replay-integrity",
        path="storage/vector_set_integrity.py",
        before="and findings == bundle.vector_findings",
        after="and True",
        case="tests/evidence/test_vector_set_replay.py::test_set_rebuild_rejects_tamper_and_rolls_back_without_network",
        runner="pytest",
    ),
    Mutation(
        name="vector-set-diff-order",
        path="storage/evidence_store.py",
        before="if current != set(bundle.prior_cache_event_ids):",
        after="if False:",
        case="tests/evidence/test_vector_set_replay.py::test_set_diff_duplicate_is_noop_and_missing_or_out_of_order_refused",
        runner="pytest",
    ),
    Mutation(
        name="vector-dbscan-insufficient",
        path="evidence/vector_sets.py",
        before="if len(valid) < params.min_samples:",
        after="if False:",
        case="tests/evidence/test_vector_sets.py::test_dbscan_insufficient_observable",
        runner="pytest",
    ),
    Mutation(
        name="vector-dbscan-stable-id",
        path="evidence/vector_sets.py",
        before="vector_hash([group[0].asset_id, config])",
        after="vector_hash([group[-1].asset_id, config])",
        case="tests/evidence/test_vector_sets.py::test_cluster_id_uses_minimum_member_and_configuration",
        runner="pytest",
    ),
    Mutation(
        name="vector-gap-target-difference",
        path="evidence/vector_sets.py",
        before=(
            "{m.subject.asset_id for m in scope.targets} - {s.subject.asset_id for s in references}"
        ),
        after=(
            "{m.subject.asset_id for m in scope.targets} | {s.subject.asset_id for s in references}"
        ),
        case="tests/evidence/test_vector_sets.py::test_gap_difference_comparison_count_observable",
        runner="pytest",
    ),
    Mutation(
        name="vector-gap-failed-reference",
        path="evidence/vector_sets.py",
        before="if not references or any(s.failure is not None for s in references):",
        after="if not references:",
        case="tests/evidence/test_vector_sets.py::test_gap_failed_reference_observable",
        runner="pytest",
    ),
    Mutation(
        name="vector-set-sample-cap",
        path="evidence/vector_sets.py",
        before="len(samples) > params.max_samples\n        or len(valid)",
        after="False\n        or len(valid)",
        case="tests/evidence/test_vector_set_capacity.py::test_set_sample_limit_5000_and_5001_rejection",
        runner="pytest",
    ),
    Mutation(
        name="vector-set-pair-cap",
        path="evidence/vector_sets.py",
        before="len(valid) * (len(valid) - 1) // 2 > params.max_candidate_pairs",
        after="False",
        case="tests/evidence/test_vector_set_capacity.py::test_set_pair_limit_249571_accepts_250278_refuses",
        runner="pytest",
    ),
    Mutation(
        name="vector-gap-comparison-cap",
        path="evidence/vector_sets.py",
        before="len(targets) * len(references) > params.max_reference_comparisons",
        after="False",
        case="tests/evidence/test_vector_set_capacity.py::test_gap_exact_250000_comparisons_and_one_over_refuses",
        runner="pytest",
    ),
)
