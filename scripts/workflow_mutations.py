# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Workflow and routing guard mutations with focused behavioral assertions."""

from scripts.mutation_models import Mutation

WORKFLOW_MUTATIONS = (
    Mutation(
        name="workflow-resume-authorization",
        path="runtime/workflow_graph.py",
        before="authorize_resume(self.db, self.run_id, request.plan_id, self.pending_plan())",
        after="pass",
        case=(
            "tests/workflows/test_authorization.py::"
            "test_forged_workflow_resumes_are_denied_and_audited"
        ),
        runner="pytest",
    ),
    Mutation(
        name="intent-margin",
        path="routing/intent.py",
        before="if lead >= trigger.margin:",
        after="if True:",
        case="tests/routing/test_intent.py::test_margin_when_two_workflows_tie_requires_classifier",
        runner="pytest",
    ),
    Mutation(
        name="intent-classifier-candidate-bound",
        path="routing/intent.py",
        before="CLASSIFIER_CANDIDATE_LIMIT = 3",
        after="CLASSIFIER_CANDIDATE_LIMIT = 4",
        case=(
            "tests/routing/test_recall.py::"
            "test_classifier_candidate_limit_when_four_positive_scores_rejects_fourth"
        ),
        runner="pytest",
    ),
    Mutation(
        name="intent-classifier-literal-verification",
        path="routing/intent.py",
        before="verified = not _excluded(scoped, workflow) and any(",
        after="verified = True or not _excluded(scoped, workflow) and any(",
        case=(
            "tests/routing/test_recall.py::"
            "test_classifier_verification_when_candidate_has_no_literal_anchor_rejects"
        ),
        runner="pytest",
    ),
    Mutation(
        name="intent-classifier-write-confirmation",
        path="runtime/graph.py",
        before="if self.workflow_confirmation_required and call.name not in {",
        after="if False and call.name not in {",
        case=(
            "tests/routing/test_confirmation.py::"
            "test_classified_write_when_model_calls_action_stops_before_mutation_then_user_can_start"
        ),
        runner="pytest",
    ),
    Mutation(
        name="intent-request-negation-scope",
        path="routing/scopes.py",
        before="        _NEGATION.search(text)\n",
        after="        False\n",
        case="tests/routing/test_scopes.py::test_negated_named_workflow_when_high_score_has_no_route",
        runner="pytest",
    ),
    Mutation(
        name="workflow-cycle",
        path="workflows/validation.py",
        before="errors.extend(cycle_errors(definition, source))",
        after="pass",
        case="tests/workflows/test_definitions.py::test_cycles_return_located_errors",
        runner="pytest",
    ),
    Mutation(
        name="fallback-failure-settlement",
        path="routing/accounting.py",
        before="self._settle_failure(request, reservation.id, started, route)",
        after="None",
        case=(
            "tests/routing/test_fallback.py::"
            "test_transient_protocol_failure_when_backup_configured_settles_each_attempt[429-openai]"
        ),
        runner="pytest",
    ),
)
