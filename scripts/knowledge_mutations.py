# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Knowledge goldens detect lost review labels and unsafe identifier tokenization."""

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
        path="core/catalog_vocabulary.py",
        before="[A-Za-z][A-Za-z0-9_]*(?:[./][A-Za-z][A-Za-z0-9_]*)*",
        after="[A-Za-z][A-Za-z0-9]*(?:[./][A-Za-z][A-Za-z0-9]*)*",
        case="38-ask-knowledge-upstream",
    ),
    Mutation(
        name="knowledge-unsupported-route",
        path="ask/service.py",
        before="if knowledge is not None:",
        after="if knowledge is not None and not knowledge.unsupported_phrasing:",
        case=(
            "tests/ask/test_knowledge_outcomes.py::"
            "test_unsupported_knowledge_question_cannot_fall_back_to_metric_values"
        ),
        runner="pytest",
    ),
    Mutation(
        name="knowledge-rejected-other-link",
        path="ask/knowledge_claims.py",
        before='        and link.assertion.status != "rejected"',
        after="",
        case=(
            "tests/ask/test_knowledge_claims.py::"
            "test_accepted_ownership_survives_rejected_other_link"
        ),
        runner="pytest",
    ),
)
