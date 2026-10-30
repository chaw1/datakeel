# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Regression anchors for one-sentence planning, chain execution and label drafting."""

from scripts.mutation_models import Mutation

_EXAMPLES = "tests/intents/test_examples.py::"
_CHAINS = "tests/intents/test_chains.py::"
_ENTRY = "tests/intents/test_agent_entry.py::"
_DRAFTS = "tests/intents/test_label_drafts.py::"
_GROUNDING = "tests/intents/test_grounding.py::"
_DEFAULTS = "tests/intents/test_fill_defaults.py::"
_CHECKS = "tests/intents/test_plan_checks.py::"
_SOURCES = "tests/intents/test_draft_sources.py::"

INTENT_MUTATIONS = (
    Mutation(
        name="intent-overreach-refused-while-planning",
        path="intents/validate.py",
        before='    if not granted and (project_known or "project_id" not in missing):',
        after="    if False:",
        # FIX1: permission is refused earlier (resolve.overreach); this check still guards a
        # project that only becomes known while filling.
        case=_CHECKS + "test_step_check_still_refuses_a_project_the_speaker_does_not_manage",
        runner="pytest",
    ),
    Mutation(
        name="intent-unknown-name-is-asked-not-guessed",
        path="intents/fill.py",
        before="    return _ask(field, step, candidates(pool), state.language, said or value)",
        after="    return pool[0].id if pool else _ask(field, step, [], state.language, value)",
        case=_EXAMPLES + "test_unknown_person_is_asked_with_candidates_and_the_reply_resumes",
        runner="pytest",
    ),
    Mutation(
        name="chain-waits-for-signature",
        path="intents/chains.py",
        before=(
            '        if plan.requires_approval:\n            return "waiting", plan.id, None, None'
        ),
        after="",
        case=_CHAINS + "test_confirmed_chain_stops_for_each_signature_and_matches_manual_receipts",
        runner="pytest",
    ),
    Mutation(
        name="chain-resume-reuses-earlier-target-plans",
        path="intents/chains.py",
        before="        if plan_id:\n            existing = _existing(",
        after="        if False:\n            existing = _existing(",
        case=_EXAMPLES + "test_partly_finished_fan_out_resumes_only_the_failed_target",
        runner="pytest",
    ),
    Mutation(
        name="chain-resume-resubmits-a-rejected-step",
        path="intents/chains.py",
        before='    if plan.status == "REJECTED" and not resuming:',
        after='    if plan.status == "REJECTED":',
        case=_CHAINS + "test_rejected_step_fails_and_resume_asks_for_a_new_signature",
        runner="pytest",
    ),
    Mutation(
        name="chain-runs-only-for-its-requester",
        path="storage/intent_chains.py",
        before="        if chain.actor != actor:",
        after="        if False:",
        case="tests/intents/test_transports.py::test_http_refuses_another_person_and_changes_nothing",
        runner="pytest",
    ),
    Mutation(
        name="planner-needs-scripted-opt-in",
        path="intents/turns.py",
        before="        engaged = isinstance(head, ScriptedResponse) and head.agent == AGENT_NAME",
        after="        engaged = True",
        case=_ENTRY + "test_scripts_without_a_planner_entry_never_reach_the_planner",
        runner="pytest",
    ),
    Mutation(
        name="planner-needs-page-context",
        path="intents/turns.py",
        before='    if context is None:\n        return "off"',
        after="",
        case=_ENTRY + "test_messages_without_page_context_keep_the_free_conversation",
        runner="pytest",
    ),
    Mutation(
        name="language-gate-requires-phrases",
        path="ontology/language_check.py",
        before='            gaps.append(f"phrases.{language}")',
        after="            pass",
        case="tests/intents/test_language_gate.py::test_gate_names_an_entry_registered_without_wording",
        runner="pytest",
    ),
    Mutation(
        name="draft-keeps-every-source-category",
        path="label_drafts/model.py",
        before="    baseline = build_labels(inputs)\n",
        after="    baseline = build_labels(inputs)[:1]\n",
        case=_DRAFTS + "test_recorded_model_draft_keeps_every_category_and_drops_invented_samples",
        runner="pytest",
    ),
    Mutation(
        name="draft-drops-invented-sample-examples",
        path="label_drafts/model.py",
        before="            if value.sample_id in samples:",
        after="            if True:",
        case=_DRAFTS + "test_recorded_model_draft_keeps_every_category_and_drops_invented_samples",
        runner="pytest",
    ),
    Mutation(
        name="draft-requires-signature",
        path="actions/label_draft_parameters.py",
        before='    "draft_label_set": (\n        "production:manage",\n        False,',
        after='    "draft_label_set": (\n        "production:manage",\n        True,',
        case=_DRAFTS + "test_draft_sentence_plans_one_signed_step_and_writes_nothing",
        runner="pytest",
    ),
    Mutation(
        name="intent-write-container-must-be-named",
        path="intents/fill.py",
        before=(
            "    if len(found) == 1 and "
            "(only or grounded(field, found[0], state.text, page, said)):"
        ),
        after="    if len(found) == 1:",
        case=_GROUNDING + "test_unnamed_single_project_copied_by_the_model_is_asked",
        runner="pytest",
    ),
    Mutation(
        name="intent-only-reads-default-to-single-container",
        path="intents/fill.py",
        before="    single = step.action in PARAMETER_MODELS",
        after="    single = True",
        case=_GROUNDING + "test_a_write_missing_its_project_asks_even_with_one_project",
        runner="pytest",
    ),
    Mutation(
        name="intent-project-named-after-its-label-set",
        path="intents/fill.py",
        before='    if step.action == "create_project" and "name" not in params and names:',
        after="    if False:",
        case=_GROUNDING + "test_project_created_with_its_label_set_is_named_after_it",
        runner="pytest",
    ),
    Mutation(
        name="intent-revocation-keeps-request-as-reason",
        path="intents/fill.py",
        before='    if "reason" in fields and "reason" not in params and text:',
        after="    if False:",
        case=_DEFAULTS + "test_revocation_keeps_the_persons_words_as_its_reason",
        runner="pytest",
    ),
    Mutation(
        name="intent-registry-read-prefix-dropped",
        path="intents/model_parse.py",
        before="        if bare in PARAMETER_MODELS and action not in PARAMETER_MODELS:",
        after="        if False:",
        case=_DEFAULTS + "test_read_prefix_copied_from_the_registry_is_dropped",
        runner="pytest",
    ),
    # FIX1: the mutant drops unknown parameters silently; the planner must report them.
    Mutation(
        name="intent-unknown-model-params-dropped",
        path="intents/fill.py",
        before="            unknown[key] = value",
        after="            continue",
        case=_CHECKS + "test_unknown_parameters_get_one_repair_round_then_a_question",
        runner="pytest",
    ),
    Mutation(
        name="intent-recipe-needs-every-detail",
        path="intents/planner.py",
        before="    if recipe is not None and (not model or recipe_covers(turn.text)):",
        after="    if recipe is not None:",
        case=_CHECKS + "test_rules_take_the_fast_path_only_when_they_use_every_detail",
        runner="pytest",
    ),
    Mutation(
        name="intent-me-is-the-speaker",
        path="intents/fill.py",
        before='    if kind == "user" and value.strip().casefold() in SELF_WORDS:',
        after="    if False:",
        case=_CHECKS + "test_me_is_the_speaker_and_positions_follow_the_task_list",
        runner="pytest",
    ),
    Mutation(
        name="intent-permission-before-questions",
        path="intents/resolve.py",
        before="        refused = overreach(self.db, draft.steps, self.state, self.catalog)",
        after="        refused = None",
        case=_CHECKS + "test_a_write_the_speaker_may_not_do_is_refused_before_any_question",
        runner="pytest",
    ),
    Mutation(
        name="intent-every-sentence-is-answered",
        path="intents/planner.py",
        before="            return unsupported(turn.text, language)",
        after="            return None",
        case=_CHECKS + "test_nothing_registered_fits_gets_a_plain_answer_listing_what_works",
        runner="pytest",
    ),
    Mutation(
        name="intent-edit-starts-from-current-version",
        path="intents/edits.py",
        before="    labels = _apply(current, edit)",
        after='    labels = _apply(current.model_copy(update={"labels": ()}), edit)',
        case=_CHECKS + "test_adding_a_label_keeps_the_existing_labels_and_shows_the_change",
        runner="pytest",
    ),
    Mutation(
        name="intent-edit-derives-its-migration",
        path="intents/edits.py",
        before=(
            '    params["migration"] = needed_migration(base, labels, edit) '
            "if base is not None else []"
        ),
        after='    params["migration"] = []',
        case=_CHECKS + "test_renaming_and_removing_labels_carry_their_migration_to_execution",
        runner="pytest",
    ),
    Mutation(
        name="intent-new-object-id-from-its-name",
        path="intents/fill.py",
        before="        fresh = new_object_field(step.action, params)",
        after="        fresh = None",
        case=_CHECKS + "test_new_objects_take_their_id_from_their_name_and_skill_grants_add",
        runner="pytest",
    ),
    Mutation(
        name="intent-skill-grant-adds-to-held",
        path="intents/fill.py",
        before=(
            '        params = prepare_user_edit(db, params) if step.action == "manage_users" '
            "else params"
        ),
        after="        params = dict(params)",
        case=_CHECKS + "test_new_objects_take_their_id_from_their_name_and_skill_grants_add",
        runner="pytest",
    ),
    Mutation(
        name="intent-operation-needs-asked-first",
        path="intents/validate.py",
        before=(
            "        name for name in operation_needs(step.action, step.params) "
            "if name not in missing"
        ),
        after="        name for name in () if name not in missing",
        case=_CHECKS + "test_new_objects_take_their_id_from_their_name_and_skill_grants_add",
        runner="pytest",
    ),
    Mutation(
        name="intent-subset-never-widens",
        path="intents/validate.py",
        before="    if wider_than_said(step, state.text):",
        after="    if False:",
        case=_CHECKS + "test_a_subset_resolves_to_exact_files_and_never_widens",
        runner="pytest",
    ),
    Mutation(
        name="intent-card-shows-final-params",
        path="intents/validate.py",
        before="    details = describe_step(db, chain_step, catalog, language)",
        after="    details = []",
        case=_CHECKS + "test_cards_show_names_and_marked_defaults_and_questions_offer_few_choices",
        runner="pytest",
    ),
    Mutation(
        name="intent-version-follows-earlier-step",
        path="intents/validate.py",
        before="    step = paired_versions(step)",
        after="    step = step.model_copy()",
        case=_CHECKS
        + "test_a_version_left_out_beside_an_earlier_step_s_id_is_taken_from_that_step",
        runner="pytest",
    ),
    Mutation(
        name="draft-plan-counts-sources-like-execution",
        path="storage/label_drafts.py",
        before=(
            "    return estimate_cost(profile, count + len(sources.examples), "
            "len(sources.categories))"
        ),
        after="    return estimate_cost(profile, count)",
        case=_SOURCES + "test_planned_budget_counts_the_same_sources_execution_checks",
        runner="pytest",
    ),
    Mutation(
        name="draft-every-kind-list-becomes-labels",
        path="label_drafts/standards.py",
        before='        if decision == "category" and listing is not None:',
        after='        if decision == "category" and listing is not None and not categories:',
        case=_SOURCES + "test_every_kind_list_becomes_a_label_subtree_and_states_become_attributes",
        runner="pytest",
    ),
    Mutation(
        name="draft-billed-failure-recorded",
        path="label_drafts/model.py",
        before="        raise ValidationError(message) from error\n    return outcome.model_copy(",
        after="        raise\n    return outcome.model_copy(",
        case=_SOURCES + "test_failed_model_answer_is_recorded_with_its_tokens_and_cost",
        runner="pytest",
    ),
    Mutation(
        name="draft-text-model-thinking-off",
        path="label_drafts/model.py",
        before='        request_extra={"thinking": {"type": "disabled"}},',
        after="",
        case=_SOURCES + "test_failed_model_answer_is_recorded_with_its_tokens_and_cost",
        runner="pytest",
    ),
    Mutation(
        name="http-signer-is-the-request-person",
        path="api/routes/actions.py",
        before='    if named not in {actor, "local"}:',
        after='    if named == "nobody":',
        case="tests/intents/test_transports.py::"
        "test_a_browser_signature_is_recorded_for_the_request_s_person",
        runner="pytest",
    ),
)
