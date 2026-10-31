# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""FIX5 anchors: the flow checks what the model left open before a sentence ends."""

from scripts.mutation_models import Mutation

_FLOW = "tests/intents/test_fix5_flow.py::"

FLOW_MUTATIONS = (
    Mutation(
        name="fix5-a-fitting-action-is-checked-not-called-missing",
        path="intents/planner.py",
        before="    draft = fitted(draft)",
        after="    draft = draft.model_copy()",
        case=_FLOW + "test_an_action_that_fits_but_misses_a_value_is_asked_with_choices",
        runner="pytest",
    ),
    Mutation(
        name="fix5-a-fitting-action-refuses-without-permission",
        path="intents/planner.py",
        before="    draft = fitted(draft)",
        after="    draft = draft.model_copy()",
        case=_FLOW + "test_an_action_that_fits_but_the_speaker_may_not_run_is_refused",
        runner="pytest",
    ),
    Mutation(
        name="fix5-only-a-registered-action-fits",
        path="intents/landing.py",
        before="    if draft.fits in names:",
        after="    if draft.fits:",
        case=_FLOW + "test_only_a_request_nothing_registered_does_is_said_missing",
        runner="pytest",
    ),
    Mutation(
        name="fix5-one-choice-is-no-choice",
        path="intents/landing.py",
        before='    return chosen[0] if len(chosen) == 1 else ""',
        after='    return ""',
        case=_FLOW + "test_an_action_that_fits_but_misses_a_value_is_asked_with_choices",
        runner="pytest",
    ),
    Mutation(
        name="fix5-already-names-the-account-state",
        path="intents/already.py",
        before='    "manage_users": _account,',
        after="",
        case=_FLOW + "test_a_change_that_is_already_so_names_the_current_state",
        runner="pytest",
    ),
    Mutation(
        name="fix5-already-with-that-reviewer",
        path="intents/already.py",
        before='    "assign_tasks": _holder,',
        after="",
        case=_FLOW + "test_a_change_that_is_already_so_names_the_current_state",
        runner="pytest",
    ),
    Mutation(
        name="fix5-already-not-quarantined",
        path="intents/already.py",
        before='    if step.action == "unquarantine_files" and not any(flags):',
        after="    if False:",
        case=_FLOW + "test_a_change_that_is_already_so_names_the_current_state",
        runner="pytest",
    ),
    Mutation(
        name="fix5-several-missing-ask-the-object-with-choices",
        path="intents/validate.py",
        before="    field = missing[0] if len(missing) == 1 else next(iter(objects), None)",
        after="    field = missing[0] if len(missing) == 1 else None",
        case=_FLOW + "test_a_question_about_objects_always_offers_choices",
        runner="pytest",
    ),
    Mutation(
        name="fix5-a-named-model-is-asked-for",
        path="intents/verify.py",
        before='        or catalog.mentioned("model", text)',
        after="",
        case=_FLOW + "test_a_model_named_in_the_words_is_asked_for",
        runner="pytest",
    ),
    Mutation(
        name="fix5-a-model-named-for-a-change-is-read",
        path="intents/derived.py",
        before="    if isinstance(nested, str) and nested.strip():",
        after="    if False:",
        case=_FLOW + "test_a_model_update_reads_its_revision_from_the_catalog",
        runner="pytest",
    ),
    Mutation(
        name="fix5-a-model-is-found-by-its-name",
        path="intents/object_edits.py",
        before="        if wanted in {item.asset_ref.asset_id.casefold(), name.casefold()}:",
        after="        if wanted == item.asset_ref.asset_id.casefold():",
        case=_FLOW + "test_a_model_update_reads_its_revision_from_the_catalog",
        runner="pytest",
    ),
    Mutation(
        name="fix5-a-model-that-cannot-is-said-not-asked",
        path="intents/capability.py",
        before="    if chosen is None or _runs_prelabel(chosen):",
        after="    if True:",
        case=_FLOW + "test_a_model_that_cannot_do_the_step_is_said_not_asked",
        runner="pytest",
    ),
)
