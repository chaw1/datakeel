# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Promote known long tests without changing selection or unlisted test order."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pytest

# Exact, stable node IDs only. Sandbox scheduling belongs to its separate affinity group.
PRIORITY_NODEIDS = (
    (
        "tests/routing/test_commands.py::"
        "test_eval_command_when_offline_prints_accuracy_and_confusion"
    ),
    (
        "tests/cli/test_evaluation.py::"
        "test_legacy_eval_when_repeated_reports_full_score_and_previous_comparison"
    ),
    "tests/harness/test_evaluation.py::test_legacy_golden_cases_pass_and_results_survive_restart",
    (
        "tests/runtime/test_tracing.py::"
        "test_tracing_when_hostile_environment_runs_all_golden_without_external_socket"
    ),
    "tests/cli/test_evaluation.py::test_default_eval_includes_all_graph_conversations",
    "tests/routing/test_commands.py::test_eval_command_when_labels_diverge_returns_failure",
    "tests/routing/test_intent.py::test_frozen_routes_when_evaluated_match_every_label",
    "tests/routing/test_paraphrase_routing.py::test_no_negative_message_starts_a_workflow",
    "tests/ask/test_evaluation.py::test_cli_reports_failed_threshold_without_nonzero_exit",
    "tests/harness/test_annotation_golden.py::test_annotation_golden_rejects_erased_real_measurements",
    "tests/routing/test_result_follow_ups.py::test_no_follow_up_about_the_workflow_itself_starts_it",
    "tests/routing/test_intent.py::test_golden_inputs_when_routed_keep_frozen_workflow_and_branch",
    (
        "tests/harness/test_knowledge_evaluation.py::"
        "test_both_knowledge_states_preserve_original_metric_benchmark"
    ),
    (
        "tests/routing/test_result_follow_ups.py::"
        "test_no_outcome_follow_up_turns_a_request_into_a_question"
    ),
    "tests/ask/test_unconsumed_guard.py::test_no_fragment_category_reaches_execution",
    (
        "tests/cli/test_ask_evaluation.py::"
        "test_eval_ask_custom_suite_reports_threshold_miss_without_failed_exit"
    ),
    "tests/routing/test_paraphrase_routing.py::test_no_workflow_question_passes_verification",
    "tests/storage/test_version_diff.py::test_diff_ten_thousand_files_page_has_bounded_python_memory",
    (
        "tests/cli/test_evidence.py::"
        "test_demo_with_evidence_reuses_sources_and_reports_complete_second_run_cache"
    ),
    "tests/cli/test_release_plan.py::test_cli_release_plan_requests_budget_and_executes",
    (
        "tests/ask/test_evaluation.py::"
        "test_twenty_questions_match_independent_gold_with_complete_evidence"
    ),
    "tests/ask/test_service.py::test_all_twenty_benchmark_questions_match_independent_gold_and_replay",
    "tests/agent/test_resume.py::test_forged_resume_cases_are_denied_and_audited",
    (
        "tests/ask/test_share_service.py::"
        "test_share_questions_reject_ungrouped_or_ununderstood_conditions_before_sql"
    ),
    (
        "tests/ask/test_comparison_period_guard.py::"
        "test_explicit_baseline_unit_mismatch_clarifies_before_sql_and_preserves_the_accepted_frame"
    ),
    (
        "tests/ask/test_comparison_period_guard.py::"
        "test_matching_explicit_units_and_generic_period_comparisons_keep_the_correct_baselines"
    ),
    (
        "tests/api/test_release_budget.py::"
        "test_explicit_budget_within_ceiling_is_frozen_approved_and_executed"
    ),
    (
        "tests/ask/test_followup_chains.py::"
        "test_unregistered_concepts_in_a_conversation_answer_like_standalone_questions"
    ),
    (
        "tests/routing/test_paraphrase_routing.py::"
        "test_declared_exclusions_keep_the_classifier_but_block_selection_and_verification"
    ),
    "tests/ask/test_unconsumed_guard.py::test_every_unparsed_time_word_is_reported_as_time",
    (
        "tests/ask/test_followup_chains.py::"
        "test_time_followups_behind_a_continuation_equal_complete_questions"
    ),
    (
        "tests/harness/test_ask_evaluation.py::"
        "test_metric_change_golden_measures_both_real_answers_and_revision_change"
    ),
)


def prioritize_tests(items: list[pytest.Item]) -> None:
    """Stably move exact hinted tests first; callers decide when scheduling applies."""
    ranks = {nodeid: rank for rank, nodeid in enumerate(PRIORITY_NODEIDS)}
    items.sort(key=lambda item: ranks.get(item.nodeid, len(ranks)))
