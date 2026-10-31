# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Unconsumed-fragment, future-period and workflow-question guards with focused cases."""

from scripts.mutation_models import Mutation

_GUARD = "tests/ask/test_unconsumed_guard.py::"
_PARAPHRASE = "tests/routing/test_paraphrase_routing.py::"
_FOLLOW_UP = "tests/routing/test_result_follow_ups.py::"

GUARD_MUTATIONS = (
    Mutation(
        name="ask-unconsumed-time-guard",
        path="ask/service.py",
        before="    if leftovers.times:",
        after="    if False:",
        case=_GUARD + "test_every_unparsed_time_word_is_reported_as_time",
        runner="pytest",
    ),
    Mutation(
        name="ask-time-like-leftovers",
        path="ask/consumption.py",
        before="    times = [hit.group().strip() for hit in TIME_LIKE.finditer(text)]",
        after="    times: list[str] = []",
        case=_GUARD + "test_every_unparsed_time_word_is_reported_as_time",
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
        before="    if dimensions.issues or leftovers.conditions:",
        after="    if dimensions.issues:",
        case=_GUARD + "test_no_fragment_category_reaches_execution",
        runner="pytest",
    ),
    Mutation(
        name="ask-english-condition-leftovers",
        path="ask/consumption.py",
        before="    conditions = [*_english_conditions(text), *_chinese_conditions(text)]",
        after="    conditions = [*_chinese_conditions(text)]",
        case=_GUARD + "test_no_fragment_category_reaches_execution",
        runner="pytest",
    ),
    Mutation(
        name="ask-unsupported-calculation-guard",
        path="ask/service.py",
        before="    unsupported = [*leftovers.calculations, *rankings]",
        after="    unsupported: list[str] = []",
        case=_GUARD + "test_no_fragment_category_reaches_execution",
        runner="pytest",
    ),
    Mutation(
        name="ask-dimension-value-negation",
        path="ask/dimensions.py",
        before=(
            "        if cues.NEGATION_BEFORE.search(before) or cues.NEGATION_AFTER.match(after):"
        ),
        after="        if False:",
        case="tests/ask/test_dimension_roles.py::test_no_unsupported_dimension_role_becomes_a_slice",
        runner="pytest",
    ),
    Mutation(
        name="ask-dimension-value-compound",
        path="ask/dimensions.py",
        before="        if _compound(question, item, known):",
        after="        if False:",
        case=_GUARD + "test_no_fragment_category_reaches_execution",
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
        case="tests/ask/test_time_english.py::test_no_future_period_is_answered",
        runner="pytest",
    ),
    Mutation(
        name="routing-workflow-question-before-scoring",
        path="routing/intent.py",
        before="    request = requested_text(text)",
        after="    request = text",
        case=_PARAPHRASE + "test_no_full_keyword_question_starts_a_workflow",
        runner="pytest",
    ),
    Mutation(
        name="routing-workflow-question-before-verification",
        path="routing/intent.py",
        before=(
            "    scoped = scope_for_workflow(normalize(requested_text(text)), workflow, workflows)"
        ),
        after="    scoped = scope_for_workflow(normalize(text), workflow, workflows)",
        case=(_PARAPHRASE + "test_no_workflow_question_passes_verification"),
        runner="pytest",
    ),
    Mutation(
        name="routing-concept-required-outcome",
        path="routing/concepts.py",
        before="    if concepts.outcomes:",
        after="    if False:",
        case=_PARAPHRASE + "test_no_negative_message_starts_a_workflow",
        runner="pytest",
    ),
    Mutation(
        name="routing-outcome-follow-up-split",
        path="routing/questions.py",
        before="            return link.start()",
        after="            return None",
        case=_FOLLOW_UP + "test_no_outcome_follow_up_turns_a_request_into_a_question",
        runner="pytest",
    ),
    Mutation(
        name="routing-outcome-question-form-blanked",
        path="routing/questions.py",
        before="        return sentence[:split] + _TAIL_CUES.sub(_spaces, tail)",
        after="        return sentence[:split] + tail",
        case=_FOLLOW_UP + "test_no_outcome_follow_up_turns_a_request_into_a_question",
        runner="pytest",
    ),
    Mutation(
        name="routing-outcome-joins-request-clause",
        path="routing/questions.py",
        before="        tail = _LINK_PUNCTUATION.sub(_spaces, sentence[split:])",
        after="        tail = sentence[split:]",
        case=_FOLLOW_UP + "test_no_outcome_follow_up_turns_a_request_into_a_question",
        runner="pytest",
    ),
    Mutation(
        name="routing-workflow-focus-follow-up",
        path="routing/questions.py",
        before="    if split is not None and _WORKFLOW_FOCUS.search(sentence[split:]) is None:",
        after="    if split is not None:",
        case=_FOLLOW_UP + "test_no_follow_up_about_the_workflow_itself_starts_it",
        runner="pytest",
    ),
    Mutation(
        name="routing-concept-exclusion-verification",
        path="routing/intent.py",
        before="    verified = verified and not concept_excluded(scoped, workflow.triggers)",
        after="    verified = verified",
        case=_PARAPHRASE
        + "test_declared_exclusions_keep_the_classifier_but_block_selection_and_verification",
        runner="pytest",
    ),
    Mutation(
        name="routing-concept-exclusion-offline",
        path="routing/intent.py",
        before="            or concept_excluded(scoped, workflow.triggers)",
        after="            or False",
        case=_PARAPHRASE
        + "test_declared_exclusions_keep_the_classifier_but_block_selection_and_verification",
        runner="pytest",
    ),
)
