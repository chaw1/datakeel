# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Knowledge regressions detect lost review states, misread focus and unsafe numeric routing."""

from scripts.mutation_models import Mutation

KNOWLEDGE_MUTATIONS = (
    Mutation(
        name="knowledge-candidate-label",
        path="ask/knowledge_claims.py",
        before="relation_status=assertion.status,",
        after='relation_status="accepted",',
        case="37-ask-knowledge-owner",
    ),
    Mutation(
        name="knowledge-whole-identifiers",
        path="ask/knowledge_names.py",
        before='pattern += r"(?![A-Za-z0-9_]|[./][A-Za-z0-9_])"',
        after='pattern += r"(?![A-Za-z0-9]|[./][A-Za-z0-9_])"',
        case=(
            "tests/ask/test_knowledge_subjects.py::"
            "test_catalog_identifiers_do_not_split_underscores_and_keep_same_tier_ambiguity"
        ),
        runner="pytest",
    ),
    Mutation(
        name="knowledge-unsupported-route",
        path="ask/service.py",
        before="if knowledge is not None:",
        after="if knowledge is not None and not knowledge.unsupported_phrasing:",
        case=(
            "tests/ask/test_knowledge_outcomes.py::"
            "test_ambiguous_intent_cannot_fall_back_to_metric_values"
        ),
        runner="pytest",
    ),
    Mutation(
        name="knowledge-rejected-other-link",
        path="ask/knowledge_claims.py",
        before='return link.assertion.status == "accepted" or (',
        after='return link.assertion.status in {"accepted", "rejected"} or (',
        case=(
            "tests/ask/test_knowledge_claims.py::"
            "test_accepted_ownership_survives_rejected_other_link"
        ),
        runner="pytest",
    ),
    Mutation(
        name="knowledge-typed-focus",
        path="ask/knowledge_focus.py",
        before=(
            "if typed := _typed_focus(text, vocabulary.TYPE_QUESTION_ANCHOR) or _adjacent_focus(\n"
            "        text, vocabulary.TYPED_QUESTION\n"
            "    ):\n"
            "        return typed"
        ),
        after=(
            "if typed := _typed_focus(text, vocabulary.TYPE_QUESTION_ANCHOR) or _adjacent_focus(\n"
            "        text, vocabulary.TYPED_QUESTION\n"
            "    ):\n"
            '        return QuestionFocus(kind="list", text=typed.text, start=typed.start)'
        ),
        case=(
            "tests/ask/test_knowledge_parser.py::"
            "test_typed_table_focus_is_preserved_before_inferring_relationship"
        ),
        runner="pytest",
    ),
    Mutation(
        name="knowledge-direction-position",
        path="ask/knowledge_roles.py",
        before=(
            "for frame in re.finditer(vocabulary.EN_INPUT_FRAME, marked):\n"
            '        if frame.start("input") <= subject < frame.end("input"):\n'
            '            return _frame_result("downstream", frame, mention)'
        ),
        after=(
            "for frame in re.finditer(vocabulary.EN_INPUT_FRAME, marked):\n"
            '        if frame.start("input") <= subject < frame.end("input"):\n'
            '            return _frame_result("upstream", frame, mention)'
        ),
        case=(
            "tests/ask/test_knowledge_parser.py::"
            "test_dependency_position_distinguishes_input_subject_from_output_subject"
        ),
        runner="pytest",
    ),
    Mutation(
        name="knowledge-hierarchy-direction",
        path="ask/knowledge_parser.py",
        before='direction = "upstream" if subject_level > target_level else "downstream"',
        after='direction = "downstream" if subject_level > target_level else "upstream"',
        case=(
            "tests/ask/test_knowledge_direction_mutations.py::"
            "test_catalog_hierarchy_infers_both_directions_and_preserves_same_layer_ambiguity"
        ),
        runner="pytest",
    ),
    Mutation(
        name="knowledge-subject-result-role",
        path="ask/knowledge_roles.py",
        before='value="upstream", words=_role_words(hit, mention), rule_id="K11-subject-role"',
        after='value="downstream", words=_role_words(hit, mention), rule_id="K11-subject-role"',
        case=(
            "tests/ask/test_knowledge_direction_mutations.py::"
            "test_subject_source_and_result_roles_override_hierarchy_in_both_languages"
        ),
        runner="pytest",
    ),
    Mutation(
        name="knowledge-person-safety-guard",
        path="ask/knowledge_parser.py",
        before="return _interpret(masked, mentions, focus)",
        after='return None if focus.kind == "person" else _interpret(masked, mentions, focus)',
        case=(
            "tests/ask/test_knowledge_outcomes.py::"
            "test_requested_person_cannot_fall_back_to_metric_values"
        ),
        runner="pytest",
    ),
)
