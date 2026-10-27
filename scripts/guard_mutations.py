# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Unconsumed-fragment, future-period and workflow-question guards with focused cases."""

from scripts.mutation_models import Mutation

_GUARD = "tests/ask/test_unconsumed_guard.py::"
_PARAPHRASE = "tests/routing/test_paraphrase_routing.py::"

GUARD_MUTATIONS = (
    Mutation(
        name="ask-unconsumed-time-guard",
        path="ask/service.py",
        before="    if leftovers.times:",
        after="    if False:",
        case=_GUARD + "test_time_fragments_refuse_as_time",
        runner="pytest",
    ),
    Mutation(
        name="ask-time-like-leftovers",
        path="ask/consumption.py",
        before="    times = [hit.group().strip() for hit in TIME_LIKE.finditer(text)]",
        after="    times: list[str] = []",
        case=_GUARD + "test_time_fragments_refuse_as_time",
        runner="pytest",
    ),
    Mutation(
        name="ask-time-modifier-leftovers",
        path="ask/consumption.py",
        before="    times.extend(_time_modifiers(text, time_spans))",
        after="    times.extend([])",
        case=_GUARD + "test_modifiers_next_to_a_resolved_period_are_leftovers",
        runner="pytest",
    ),
    Mutation(
        name="ask-unconsumed-condition-guard",
        path="ask/service.py",
        before=(
            "    issues = [*dimensions.issues, "
            '*(f"未理解「{item}」" for item in leftovers.conditions)]'
        ),
        after="    issues = [*dimensions.issues]",
        case=_GUARD + "test_unconsumed_fragments_never_execute_or_return_numbers",
        runner="pytest",
    ),
    Mutation(
        name="ask-english-condition-leftovers",
        path="ask/consumption.py",
        before="    conditions = [*_english_conditions(text), *_chinese_conditions(text)]",
        after="    conditions = [*_chinese_conditions(text)]",
        case=_GUARD + "test_unconsumed_fragments_never_execute_or_return_numbers",
        runner="pytest",
    ),
    Mutation(
        name="ask-unsupported-calculation-guard",
        path="ask/service.py",
        before="    unsupported = [*leftovers.calculations, *rankings]",
        after="    unsupported: list[str] = []",
        case=_GUARD + "test_unconsumed_fragments_never_execute_or_return_numbers",
        runner="pytest",
    ),
    Mutation(
        name="ask-dimension-value-negation",
        path="ask/dimensions.py",
        before=(
            "        if cues.NEGATION_BEFORE.search(before) or cues.NEGATION_AFTER.match(after):"
        ),
        after="        if False:",
        case="tests/ask/test_dimension_roles.py::test_unsupported_dimension_roles_are_reported",
        runner="pytest",
    ),
    Mutation(
        name="ask-dimension-value-compound",
        path="ask/dimensions.py",
        before="        if _compound(question, item, known):",
        after="        if False:",
        case=_GUARD + "test_unconsumed_fragments_never_execute_or_return_numbers",
        runner="pytest",
    ),
    Mutation(
        name="ask-future-period",
        path="ask/time.py",
        before=(
            "        if issue is None and atom.interval_start is not None"
            " and atom.interval_start >= reference:"
        ),
        after="        if False:",
        case="tests/ask/test_time_english.py::test_periods_that_have_not_started_are_refused",
        runner="pytest",
    ),
    Mutation(
        name="routing-workflow-question-before-scoring",
        path="routing/intent.py",
        before="    request = requested_text(text)",
        after="    request = text",
        case=_PARAPHRASE + "test_full_keyword_matches_start_only_when_not_asked_as_a_question",
        runner="pytest",
    ),
    Mutation(
        name="routing-workflow-question-before-verification",
        path="routing/intent.py",
        before=(
            "    scoped = scope_for_workflow(normalize(requested_text(text)), workflow, workflows)"
        ),
        after="    scoped = scope_for_workflow(normalize(text), workflow, workflows)",
        case=(
            _PARAPHRASE
            + "test_questions_about_a_workflow_cannot_be_verified_even_if_a_model_selects_one"
        ),
        runner="pytest",
    ),
    Mutation(
        name="routing-concept-required-outcome",
        path="routing/concepts.py",
        before="    if concepts.outcomes:",
        after="    if False:",
        case=_PARAPHRASE + "test_questions_and_near_misses_never_start_a_workflow",
        runner="pytest",
    ),
)
