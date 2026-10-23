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
