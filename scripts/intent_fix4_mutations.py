# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""FIX4 regression anchors for the look-up-first planner: it reads only, and it stops."""

from scripts.mutation_models import Mutation

_EXPLORE = "tests/intents/test_fix4_explore.py::"

EXPLORE_MUTATIONS = (
    Mutation(
        name="fix4-explore-path-is-taken",
        path="intents/planner.py",
        before="    if access.explore:",
        after="    if False:",
        case=_EXPLORE + "test_look_ups_are_answered_and_the_plan_goes_through_the_usual_checks",
        runner="pytest",
    ),
    Mutation(
        name="fix4-explore-results-reach-the-model",
        path="intents/explore.py",
        before="        request = _followed(request, response.content, found)",
        after="        request = request",
        case=_EXPLORE + "test_look_ups_are_answered_and_the_plan_goes_through_the_usual_checks",
        runner="pytest",
    ),
    Mutation(
        name="fix4-explore-runs-reads-only",
        path="intents/explore.py",
        before="        if name not in PARAMETER_MODELS:",
        after="        if False:",
        case=_EXPLORE + "test_a_write_named_as_a_look_up_is_never_run",
        runner="pytest",
    ),
    Mutation(
        name="fix4-explore-stops-at-the-limit",
        path="intents/explore.py",
        before="    for used in range(1, EXPLORE_LIMIT + 1):",
        after="    for used in range(1, EXPLORE_LIMIT + 3):",
        case=_EXPLORE + "test_look_ups_stop_at_the_limit_and_the_last_answer_is_read_as_the_plan",
        runner="pytest",
    ),
)
