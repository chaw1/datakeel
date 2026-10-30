# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""FIX2 regression anchors for one-sentence planning, drafting and model routing.

They lock query-first task scopes, deterministic plan checks, honest failures, complete
drafts and routing to configured models only.
"""

from scripts.mutation_models import Mutation

_ROUTING = "tests/routing/test_conversation_routing.py::"
_REPAIR = "tests/intents/test_draft_repair.py::"
_COMPLETE = "tests/intents/test_draft_completeness.py::"

DRAFT_ROUTING_MUTATIONS = (
    Mutation(
        name="routing-auto-uses-the-configured-endpoint-tiers",
        path="routing/config.py",
        before="    tiers = config.endpoints.get(openai_host(settings))",
        after="    tiers = None",
        case=_ROUTING + "test_only_deepseek_configured_routes_every_tier_to_deepseek",
        runner="pytest",
    ),
    Mutation(
        name="routing-unrouted-endpoint-is-a-setup-problem",
        path="routing/config.py",
        before='    return None if known or host == OPENAI_HOST else "unrouted_endpoint"',
        after="    return None",
        case=_ROUTING
        + "test_without_a_usable_model_the_page_is_told_it_is_a_configuration_problem",
        runner="pytest",
    ),
    Mutation(
        name="draft-output-room-follows-the-label-count",
        path="label_drafts/model.py",
        before="    wanted = OUTPUT_BASE + OUTPUT_PER_LABEL * max(labels, ASSUMED_LABELS)",
        after="    wanted = OUTPUT_MIN",
        case=_REPAIR + "test_output_room_and_the_estimate_grow_with_the_label_count",
        runner="pytest",
    ),
    Mutation(
        name="draft-label-key-read-as-id",
        path="label_drafts/answer.py",
        before='    **dict.fromkeys(("key", "code", "label_id", "value"), "id"),',
        after='    **dict.fromkeys(("code", "label_id", "value"), "id"),',
        case=_REPAIR + "test_misspelt_field_names_are_mapped_without_another_call",
        runner="pytest",
    ),
    Mutation(
        name="draft-broken-answer-gets-one-repair-round",
        path="label_drafts/model.py",
        before="    if checked.problems and room is not None:",
        after="    if False:",
        case=_REPAIR + "test_unreadable_items_are_listed_for_the_repair_round",
        runner="pytest",
    ),
    Mutation(
        name="draft-missing-kind-is-described",
        path="label_drafts/complete.py",
        before="        if kind in kinds or any(item.kind == kind for item in extra):",
        after="        if True:",
        case=_COMPLETE + "test_standards_only_draft_describes_examples_and_says_so",
        runner="pytest",
    ),
    Mutation(
        name="draft-annotation-attributes-become-definitions",
        path="storage/label_drafts.py",
        before="        attributes=(*standards.attributes, *observed_attributes(observed)),",
        after="        attributes=standards.attributes,",
        case=_COMPLETE + "test_annotation_only_draft_takes_attributes_from_what_people_filled",
        runner="pytest",
    ),
    Mutation(
        name="draft-overview-drops-the-model-example-claim",
        path="label_drafts/complete.py",
        before='    kept_zh = _EXAMPLE_TALK.sub("", written_zh).strip()',
        after="    kept_zh = written_zh.strip()",
        case=_COMPLETE + "test_model_draft_overview_states_where_its_examples_really_came_from",
        runner="pytest",
    ),
    Mutation(
        name="draft-failed-calls-reach-the-cost-summary",
        path="storage/action_execution.py",
        before="            record_draft_calls(session, plan.id, plan.session_id, error.calls)",
        after="            pass",
        case=_REPAIR + "test_failed_draft_calls_reach_the_cost_summary",
        runner="pytest",
    ),
    Mutation(
        name="draft-successful-calls-reach-the-cost-summary",
        path="storage/label_drafts.py",
        before="    record_draft_calls(session, plan.id, plan.session_id, outcome.calls)",
        after="    _ = outcome.calls",
        case=_REPAIR + "test_successful_draft_calls_are_in_the_cost_summary_too",
        runner="pytest",
    ),
)

_SCOPE = "tests/intents/test_fix2_scope.py::"
_GROUP = _SCOPE + "test_a_described_group_is_read_first_and_protected_tasks_are_left_out"

PLANNING_MUTATIONS = (
    Mutation(
        name="intent-protected-tasks-left-out",
        path="intents/task_scope.py",
        before="    guarded = set(PROTECTIONS.get(action, ())) - _unlocked(spec, holder)",
        after="    guarded: set[str] = set()",
        case=_GROUP,
        runner="pytest",
    ),
    Mutation(
        name="intent-exclusions-shown-on-the-card",
        path="intents/resolve.py",
        before=(
            "            checked.append("
            "_with_exclusions(result.step, left_out.get(step.id), draft.language))"
        ),
        after="            checked.append(result.step)",
        case=_GROUP,
        runner="pytest",
    ),
    Mutation(
        name="intent-task-numbers-are-named-tasks",
        path="intents/task_scope.py",
        before="    named = _named(spec)",
        after="    named = None",
        case=_GROUP,
        runner="pytest",
    ),
    Mutation(
        name="intent-bare-tasks-never-widen",
        path="intents/group_fill.py",
        before="    if not described and not says_whole(state.text):",
        after="    if False:",
        case=_GROUP,
        runner="pytest",
    ),
    Mutation(
        name="intent-unassigned-means-unheld-and-open",
        path="intents/task_scope.py",
        before=(
            '    if is_nobody(spec.get("holder"), spec) and '
            '(task.holder is not None or task.state != "pending"):'
        ),
        after="    if False:",
        case=_SCOPE + "test_unassigned_means_nobody_holds_it_and_it_is_still_open",
        runner="pytest",
    ),
    Mutation(
        name="intent-include-unlocks-annotated",
        path="intents/task_scope.py",
        before=(
            "    unlocked: set[str] = {item for item in listed if isinstance(item, str)} & INCLUDES"
        ),
        after="    unlocked: set[str] = set()",
        case=_SCOPE + "test_saved_annotation_is_protected_unless_the_words_include_it",
        runner="pytest",
    ),
    Mutation(
        name="intent-disabled-account-gets-no-work",
        path="intents/fill.py",
        before='        if found[0].status != "active" and field in RECEIVERS:',
        after="        if False:",
        case=_SCOPE + "test_a_disabled_account_is_named_and_never_offered",
        runner="pytest",
    ),
    Mutation(
        name="intent-empty-change-is-answered",
        path="intents/resolve.py",
        before="        if all(unchanged(self.db, step) for step in checked):",
        after="        if False:",
        case=_SCOPE + "test_a_plan_that_changes_nothing_is_answered_instead_of_shown",
        runner="pytest",
    ),
    Mutation(
        name="intent-broken-rules-get-a-repair-round",
        path="intents/planner.py",
        before="    problems = draft_problems(db, draft, state, catalog)",
        after="    problems = []",
        case=_SCOPE + "test_a_reviewer_s_send_back_is_a_review_decision",
        runner="pytest",
    ),
    Mutation(
        name="intent-review-uses-the-latest-revision",
        path="intents/fill.py",
        before=(
            '    if step.action != "review_task" or "revision_id" in step.params '
            "or not isinstance(task, str):"
        ),
        after="    if True:",
        case=_SCOPE + "test_a_reviewer_s_send_back_is_a_review_decision",
        runner="pytest",
    ),
    Mutation(
        name="intent-model-steps-need-model-words",
        path="intents/verify.py",
        before="    if step.action not in MODEL_ACTIONS or asked:",
        after="    if True:",
        case=_SCOPE + "test_a_model_step_needs_words_that_ask_for_a_model",
        runner="pytest",
    ),
    Mutation(
        name="intent-model-failure-keeps-its-reason",
        path="intents/outcomes.py",
        before="        raise PlannerFailure(_reason(error)) from error",
        after='        raise PlannerFailure("provider") from error',
        case=_SCOPE + "test_failed_model_calls_are_reported_as_failures_with_the_reason",
        runner="pytest",
    ),
    Mutation(
        name="intent-model-failure-is-not-swallowed",
        path="intents/planner.py",
        before="        return failed(turn.text, failure.reason, language_of(turn.text))",
        after="        return None",
        case=_SCOPE + "test_failed_model_calls_are_reported_as_failures_with_the_reason",
        runner="pytest",
    ),
    Mutation(
        name="intent-related-actions-are-asked",
        path="intents/outcomes.py",
        before="    if not related:",
        after="    if True:",
        case=_SCOPE + "test_nothing_fits_but_related_actions_are_offered_as_a_question",
        runner="pytest",
    ),
    Mutation(
        name="intent-internal-error-said-plainly",
        path="intents/turns.py",
        before=(
            '        result = internal_error(text, language_of(text)) if mode == "model" else None'
        ),
        after="        result = None",
        case=_SCOPE + "test_internal_errors_are_said_plainly_without_the_raw_text",
        runner="pytest",
    ),
    Mutation(
        name="intent-rejected-value-without-raw-text",
        path="intents/validate.py",
        before="                others.append(bad_value(item, step.action))",
        after="                others.append(message)",
        case=_SCOPE + "test_rejected_values_are_named_without_the_raw_validator_text",
        runner="pytest",
    ),
    Mutation(
        name="intent-unregistered-action-unsupported",
        path="intents/resolve.py",
        before="            if result.step is None and current.action not in POLICIES:",
        after="            if False:",
        case="tests/intents/test_agent_entry.py::test_model_cannot_invent_identities_or_actions",
        runner="pytest",
    ),
    Mutation(
        name="chain-picks-one-item-of-an-earlier-output",
        path="intents/chains.py",
        before='        return _nth_of(found, value.get("$nth"), str(value["$ref"]))',
        after="        return found",
        case=_SCOPE + "test_a_later_step_can_take_one_package_an_earlier_split_made",
        runner="pytest",
    ),
    Mutation(
        name="intent-registry-lists-parameters",
        path="intents/model_parse.py",
        before='        lines.append(f"{kind} {signatures.get(name, name)}: {said}")',
        after='        lines.append(f"{kind} {name}: {said}")',
        case=_SCOPE + "test_the_planner_sees_every_parameter_and_asks_for_steady_json",
        runner="pytest",
    ),
    Mutation(
        name="intent-skill-list-keeps-unmentioned-skills",
        path="intents/verify.py",
        before="        lost = [item for item in held if given is not None and item not in given]",
        after="        lost: list[str] = []",
        case=_SCOPE + "test_a_full_skill_list_never_drops_skills_the_person_did_not_mention",
        runner="pytest",
    ),
    Mutation(
        name="intent-missing-choice-offers-its-values",
        path="intents/validate.py",
        before="    if field and not kind:",
        after="    if False:",
        case=_SCOPE + "test_a_missing_choice_is_asked_with_its_allowed_values",
        runner="pytest",
    ),
    Mutation(
        name="intent-role-change-is-a-binding",
        path="intents/verify.py",
        before=(
            '    if step.action != "manage_users" or params.get("operation") != "update" '
            "or not roles:"
        ),
        after="    if True:",
        case=_SCOPE + "test_a_role_is_bound_not_written_into_an_account_update",
        runner="pytest",
    ),
    Mutation(
        name="intent-files-named-by-file-name",
        path="intents/selectors.py",
        before='    elif kind == "named":',
        after="    elif False:",
        case=_SCOPE + "test_files_named_by_file_name_resolve_to_exactly_those",
        runner="pytest",
    ),
    Mutation(
        name="intent-recipe-data-phrase-is-not-a-label",
        path="intents/recipes.py",
        before="    if after and not _DATA_PHRASE.search(after):",
        after="    if after:",
        case=_SCOPE + "test_a_for_phrase_that_names_the_data_is_not_a_label",
        runner="pytest",
    ),
)

INTENT_FIX2_MUTATIONS = (*DRAFT_ROUTING_MUTATIONS, *PLANNING_MUTATIONS)
