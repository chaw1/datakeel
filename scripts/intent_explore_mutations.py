# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Read-first anchors: the look-up-first planner reads only and stops; planner requests stream."""

from scripts.mutation_models import Mutation

_EXPLORE = "tests/intents/test_read_first_explore.py::"
_CHAT = "tests/runtime/test_chat_provider.py::"

EXPLORE_MUTATIONS = (
    Mutation(
        name="explore-explore-path-is-taken",
        path="intents/planner.py",
        before="    if access.explore:",
        after="    if False:",
        case=_EXPLORE + "test_look_ups_are_answered_and_the_plan_goes_through_the_usual_checks",
        runner="pytest",
    ),
    Mutation(
        name="explore-explore-results-reach-the-model",
        path="intents/explore.py",
        before="        request, used = _followed(request, response, used, lookups)",
        after="        used += 1",
        case=_EXPLORE + "test_look_ups_are_answered_and_the_plan_goes_through_the_usual_checks",
        runner="pytest",
    ),
    Mutation(
        name="explore-explore-runs-reads-only",
        path="intents/explore.py",
        before="        if name not in PARAMETER_MODELS:",
        after="        if False:",
        case=_EXPLORE + "test_a_write_named_as_a_look_up_is_never_run",
        runner="pytest",
    ),
    Mutation(
        name="explore-explore-stops-at-the-limit",
        path="intents/explore.py",
        before="    while response.tool_calls and used < EXPLORE_LIMIT:",
        after="    while response.tool_calls and used < EXPLORE_LIMIT + 2:",
        case=_EXPLORE + "test_look_ups_stop_at_the_limit_and_the_last_answer_is_read_as_the_plan",
        runner="pytest",
    ),
    Mutation(
        name="explore-explore-calls-past-the-limit-are-not-run",
        path="intents/explore.py",
        before=(
            '        found = lookups.found(look) if used <= EXPLORE_LIMIT else "No more look-ups."'
        ),
        after="        found = lookups.found(look)",
        case=_EXPLORE + "test_several_look_ups_in_one_reply_count_against_the_limit",
        runner="pytest",
    ),
    Mutation(
        name="explore-planner-json-requests-stream",
        path="runtime/chat.py",
        before=(
            "        if request.json_output and isinstance(model, ChatOpenAI):\n"
            "            return _response(_streamed(bound, messages, request))"
        ),
        after=(
            "        if False:\n            return _response(_streamed(bound, messages, request))"
        ),
        case=_CHAT + "test_openai_when_json_output_requested_streams_and_joins_the_answer",
        runner="pytest",
    ),
)
