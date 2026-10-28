# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Question chart and follow-up guards extend the measured mutation corpus."""

from scripts.mutation_models import Mutation

ASK_CHART_MUTATIONS = (
    Mutation(
        name="ask-chart-category-limit",
        path="ask/charts.py",
        before="_MAX_CATEGORIES = 30",
        after="_MAX_CATEGORIES = 31",
        case="tests/ask/test_chart_guards.py::test_chart_category_limit_is_hard",
        runner="pytest",
    ),
    Mutation(
        name="ask-chart-long-labels",
        path="ask/charts.py",
        before="_MAX_LABEL_LENGTH = 12",
        after="_MAX_LABEL_LENGTH = 120",
        case="tests/ask/test_chart_guards.py::test_chart_long_labels_are_horizontal",
        runner="pytest",
    ),
    Mutation(
        name="ask-chart-dimension-limit",
        path="ask/charts.py",
        before="_MAX_DIMENSIONS = 2",
        after="_MAX_DIMENSIONS = 3",
        case="tests/ask/test_chart_guards.py::test_chart_extra_dimensions_are_tabular",
        runner="pytest",
    ),
    Mutation(
        name="ask-conversation-owner",
        path="storage/ask_conversations.py",
        before="if row is None or row.actor != actor:",
        after="if row is None:",
        case=("tests/ask/test_conversations.py::test_cross_actor_open_never_returns_owned_history"),
        runner="pytest",
    ),
    Mutation(
        name="ask-comparison-percentage",
        path="ask/comparisons.py",
        before="else delta / abs(before) * 100",
        after="else delta / abs(before)",
        case=(
            "tests/ask/test_comparisons.py::"
            "test_time_buckets_align_by_calendar_period_not_absolute_date"
        ),
        runner="pytest",
    ),
    Mutation(
        name="ask-deleted-tool-replay",
        path="ontology/tooling.py",
        before='if previous.name == "ask_data":',
        after="if False:",
        case=(
            "tests/ontology/test_ask_conversations.py::"
            "test_deleted_question_thread_cannot_replay_cached_agent_tool_answer"
        ),
        runner="pytest",
    ),
    Mutation(
        name="ask-followup-unconsumed-suffix",
        path="ask/followup.py",
        before="if unknown or not understood:",
        after="if False:",
        case="tests/ask/test_followup_chains.py::test_unknown_followup_suffix_requires_clarification",
        runner="pytest",
    ),
    Mutation(
        name="ask-followup-fresh-question-gate",
        path="ask/followup.py",
        before="    if cues.edit_cue(question) or consumed:\n        return True",
        after="    return True",
        case=(
            "tests/ask/test_followup_chains.py::"
            "test_unregistered_concepts_in_a_conversation_answer_like_standalone_questions"
        ),
        runner="pytest",
    ),
    Mutation(
        name="ask-followup-continuation-consumed",
        path="ask/followup.py",
        before="        consumed.extend(cues.continuation_spans(request.question))",
        after="        pass",
        case=(
            "tests/ask/test_followup_chains.py::"
            "test_time_followups_behind_a_continuation_equal_complete_questions"
        ),
        runner="pytest",
    ),
    Mutation(
        name="ask-comparison-week-alignment",
        path="ask/comparisons.py",
        before='if frame.comparison == "year_over_year" or calendar_aligned',
        after='if frame.time_grain != "day" or months',
        case=(
            "tests/ask/test_comparisons.py::"
            "test_previous_week_daily_buckets_align_across_month_boundary"
        ),
        runner="pytest",
    ),
    Mutation(
        name="ask-negated-query-edits",
        path="ask/followup_cues.py",
        before=" or _negated_edits(question)",
        after="",
        case=(
            "tests/ask/test_special_intent_guards.py::"
            "test_negated_special_intents_in_complete_questions_clarify_without_numbers"
        ),
        runner="pytest",
    ),
    Mutation(
        name="ask-article-before-year",
        path="ask/followup_cues.py",
        before=r'r"(?:the\s+)?last\s+year"',
        after=r'r"last\s+year"',
        case=(
            "tests/ask/test_followup_rules.py::"
            "test_article_before_last_year_preserves_the_original_temporal_parse"
        ),
        runner="pytest",
    ),
    Mutation(
        name="ask-share-display-intent",
        path="ask/followup.py",
        before=(
            "or any(cues.SHARE.fullmatch(request.question[start:end]) for start, end in consumed),"
        ),
        after="or False,",
        case=(
            "tests/ask/test_share_service.py::"
            "test_share_followups_inherit_display_intent_and_complete_topics_reset_it"
        ),
        runner="pytest",
    ),
    Mutation(
        name="ask-share-requires-grouping",
        path="ask/service.py",
        before="if frame.share_of_result_rows and not (frame.group_by or frame.time_grain):",
        after="if False:",
        case=(
            "tests/ask/test_share_service.py::"
            "test_share_questions_reject_ungrouped_or_ununderstood_conditions_before_sql"
        ),
        runner="pytest",
    ),
    Mutation(
        name="ask-comparison-explicit-period-unit",
        path="ask/service.py",
        before="if comparison_unit_mismatch(question, frame):",
        after="if False:",
        case=(
            "tests/ask/test_comparison_period_guard.py::"
            "test_explicit_baseline_unit_mismatch_clarifies_before_sql_and_preserves_the_accepted_frame"
        ),
        runner="pytest",
    ),
)
