# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Named fake vector safety and semantic anchors, run only in disposable copies."""

from scripts.mutation_models import Mutation
from scripts.vector_lock_mutations import VECTOR_LOCK_MUTATIONS
from scripts.vector_set_mutations import VECTOR_SET_MUTATIONS

VECTOR_MUTATIONS = (
    *VECTOR_LOCK_MUTATIONS,
    *VECTOR_SET_MUTATIONS,
    Mutation(
        name="vector-parameter-wording",
        path="intents/field_names.py",
        before='"max_candidate_pairs": (',
        after='"unregistered_candidate_pairs": (',
        case="tests/intents/test_language_gate.py::test_vector_operator_parameters_and_nested_policy_have_bilingual_words",
        runner="pytest",
    ),
    Mutation(
        name="vector-enum-wording",
        path="intents/field_names.py",
        before='"we-e2-fake-v1": (',
        after='"unregistered-fake-version": (',
        case="tests/intents/test_language_gate.py::test_vector_operator_parameters_and_nested_policy_have_bilingual_words",
        runner="pytest",
    ),
    Mutation(
        name="vector-offline-external-block",
        path="tests/offline_network.py",
        before="return address.is_loopback",
        after="return True",
        case="tests/test_offline_network.py::test_external_dns_and_connections_fail_before_original_functions[192.0.2.1]",
        runner="pytest",
        source_root="repository",
    ),
    Mutation(
        name="vector-prepare-eligible-pairs",
        path="evidence/vector_plan_sets.py",
        before="sum(prepare_wire(file, embed).frozen.failure is None for file in selected)",
        after="len(selected)",
        case="tests/evidence/test_vector_capacity.py::test_prepare_and_worker_invalid_input_at_exact_pair_limit_are_partial[invalid-utf8]",
        runner="pytest",
    ),
    Mutation(
        name="vector-runtime-eligible-pairs",
        path="evidence/vector_duplicate.py",
        before="len(valid) * (len(valid) - 1) // 2",
        after="len(samples) * (len(samples) - 1) // 2",
        case="tests/evidence/test_vector_capacity.py::test_direct_pairs_failed_samples_do_not_consume_comparison_budget",
        runner="pytest",
    ),
    Mutation(
        name="vector-schema-owner",
        path="persistence/vector.py",
        before='owner="vector_store"',
        after='owner="worker_store"',
        case="tests/storage/test_vector_schema.py::test_vector_contribution_has_independent_canonical_owner",
        runner="pytest",
    ),
    Mutation(
        name="vector-schema-lease",
        path="worker_store/rows.py",
        before="    lease_expires_at: Mapped[float | None] = mapped_column(Float, nullable=True)\n",
        after="",
        case="tests/storage/test_vector_schema.py::test_ddl_preserves_every_main_table_except_explicit_inventory_additions[sqlite]",
        runner="pytest",
    ),
    Mutation(
        name="vector-human-entry",
        path="storage/vector_authorization.py",
        before="and plan.external",
        after="and False",
        case="tests/evidence/test_vector_boundaries.py::test_tool_approval_guard_is_observable",
        runner="pytest",
    ),
    Mutation(
        name="vector-persistent-request-count",
        path="storage/vector_budget.py",
        before="account.requests += 1",
        after="account.requests += 0",
        case="tests/evidence/test_vector_budget.py::test_concurrent_duplicate_reservation_is_atomic_and_durable",
        runner="pytest",
    ),
    Mutation(
        name="vector-no-redispatch",
        path="storage/vector_budget.py",
        before='row.state != "RESERVED"',
        after='row.state not in {"RESERVED", "SENDING"}',
        case="tests/evidence/test_vector_boundaries.py::test_redispatch_guard_is_observable",
        runner="pytest",
    ),
    Mutation(
        name="vector-direct-pair",
        path="evidence/vector_duplicate.py",
        before="if similarity >= params.threshold:",
        after="if True:",
        case="tests/evidence/test_vector_algorithm.py::test_direct_pairs_are_nontransitive_and_input_order_invariant",
        runner="pytest",
    ),
    Mutation(
        name="vector-failed-publication",
        path="persistence/task_vector.py",
        before="if error:\n        return ()",
        after="if error:\n        return evidence",
        case="tests/evidence/test_vector_boundaries.py::test_error_finish_discards_all_pending_vectors",
        runner="pytest",
    ),
)
