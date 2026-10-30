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

INTENT_MUTATIONS = (
    Mutation(
        name="intent-overreach-refused-while-planning",
        path="intents/validate.py",
        before='    if not granted and (project_known or "project_id" not in missing):',
        after="    if False:",
        case=_EXAMPLES + "test_annotator_is_refused_at_planning_with_the_missing_scope",
        runner="pytest",
    ),
    Mutation(
        name="intent-unknown-name-is-asked-not-guessed",
        path="intents/fill.py",
        before="    return _ask(field, step, candidates(pool), state.language, value)",
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
        before="    merged = list(baseline)",
        after="    merged = list(baseline)[:1]",
        case=_DRAFTS + "test_recorded_model_draft_keeps_every_category_and_drops_invented_samples",
        runner="pytest",
    ),
    Mutation(
        name="draft-drops-invented-sample-examples",
        path="label_drafts/model.py",
        before="                if value.sample_id in samples:",
        after="                if True:",
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
        before="    if len(found) == 1 and (only or grounded(field, found[0], state.text, page)):",
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
        before='    if step.action == "revoke_assignment" and "reason" not in params and text:',
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
    Mutation(
        name="intent-unknown-model-params-dropped",
        path="intents/fill.py",
        before="        if name in fields:\n            params.setdefault(name, value)",
        after="        params.setdefault(name, value)",
        case=_DEFAULTS + "test_unknown_keys_are_dropped_and_task_plurals_renamed",
        runner="pytest",
    ),
)
