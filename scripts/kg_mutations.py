# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Graph extraction regressions require real assertion failures at three production guards."""

from scripts.mutation_models import Mutation

KG_MUTATIONS = (
    Mutation(
        name="kg-endpoint-verification",
        path="kg/assembly.py",
        before=(
            "    if head is None:\n"
            '        issues.append(VerificationIssue(code="head", role="head"))\n'
            "    if tail is None:\n"
            '        issues.append(VerificationIssue(code="tail", role="tail"))\n'
        ),
        after="",
        case="tests/harness/test_kg_mutations.py::test_missing_endpoints_cannot_be_verified",
        runner="pytest",
    ),
    Mutation(
        name="kg-preserve-needs-review",
        path="kg/assembly.py",
        before="        drafts.append(_relation_draft(relation, resolved, schema, source))",
        after=(
            "        candidate = _relation_draft(relation, resolved, schema, source)\n"
            '        if candidate.verification == "verified":\n'
            "            drafts.append(candidate)"
        ),
        case="tests/harness/test_kg_mutations.py::test_unverified_relations_are_not_discarded",
        runner="pytest",
    ),
    Mutation(
        name="kg-cache-model-identity",
        path="kg/cache.py",
        before='    configuration["model"] = profile.model',
        after='    configuration.pop("model", None)',
        case="tests/harness/test_kg_mutations.py::test_model_name_participates_in_cache_identity",
        runner="pytest",
    ),
)
