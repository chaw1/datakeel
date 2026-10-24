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
        before='(\n        "table",\n',
        after='(\n        "person",\n',
        case=(
            "tests/ask/test_knowledge_parser.py::"
            "test_typed_table_focus_is_preserved_before_inferring_relationship"
        ),
        runner="pytest",
    ),
    Mutation(
        name="knowledge-direction-position",
        path="ask/knowledge_focus.py",
        before='value="downstream" if after else "upstream"',
        after='value="upstream" if after else "downstream"',
        case=(
            "tests/ask/test_knowledge_parser.py::"
            "test_dependency_position_distinguishes_input_subject_from_output_subject"
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
