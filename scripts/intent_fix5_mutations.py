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
)
