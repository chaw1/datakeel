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
        path="core/link_matching.py",
        before="[A-Za-z][A-Za-z0-9_]*(?:[./][A-Za-z][A-Za-z0-9_]*)*",
        after="[A-Za-z][A-Za-z0-9]*(?:[./][A-Za-z][A-Za-z0-9]*)*",
        case="38-ask-knowledge-upstream",
    ),
)
