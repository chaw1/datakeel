# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Original guard mutations, run first and in this order before every feature catalog."""

from scripts.mutation_models import Mutation

CORE_MUTATIONS = (
    Mutation(
        name="resume-authorization",
        path="runtime/graph.py",
        before=(
            "authorize_resume(self.db, self.conversation_id, request.plan_id, self.pending_plan())"
        ),
        after="pass",
        case="tests/agent/test_resume.py::test_forged_resume_cases_are_denied_and_audited",
        runner="pytest",
    ),
    Mutation(
        name="tool-call-idempotency",
        path="storage/tool_invocations.py",
        before="if call_id is None:",
        after="if True:",
        case=(
            "tests/runtime/test_recovery.py::"
            "test_recovery_when_killed_after_interrupt_preserves_one_action_and_tool_call"
        ),
        runner="pytest",
    ),
    Mutation(
        name="repeated-call",
        path="agent/guards.py",
        before="if self.calls[signature] >= REPEAT_LIMIT:",
        after="if False:",
        case="07-repeated-loop",
    ),
    Mutation(
        name="budget-reservation",
        path="storage/budget_service.py",
        before="exceeded = any(",
        after="exceeded = False and any(",
        case="08-budget",
    ),
    Mutation(
        name="dry-run", path="agent/confirm.py", before=" or dry_run:", after=":", case="11-dry-run"
    ),
    Mutation(
        name="human-approval",
        path="agent/confirm.py",
        before=" or plan.requires_approval",
        after="",
        case="04-irreversible-approval",
    ),
    Mutation(
        name="canonical-parameters",
        path="storage/action_requests.py",
        before="if request.canonical_params is not None and digest(request.canonical_params)",
        after="if False and digest(request.canonical_params)",
        case="06-frozen-approval",
    ),
    Mutation(
        name="target-state",
        path="storage/action_planning.py",
        before=(
            "if snapshot_digest(session, params, current) != plan.state_digest "
            "or current.truncated:"
        ),
        after="if False:",
        case="06-frozen-approval",
    ),
    Mutation(
        name="missing-annotation-unknown",
        path="operators/evidence/label_gap.py",
        before='value = "unknown"',
        after='value = "absent"',
        case="14-evidence-unknown",
    ),
    Mutation(
        name="near-duplicate-threshold",
        path="operators/evidence/near_duplicate_hashes.py",
        before="if (distance := (left_hash ^ right_hash).bit_count()) <= threshold",
        after="if (distance := (left_hash ^ right_hash).bit_count()) <= threshold + 4",
        case=(
            "tests/operators/evidence/test_near_duplicate.py::"
            "test_near_duplicate_when_chain_images_supplied_does_not_infer_endpoint_pair"
        ),
        runner="pytest",
    ),
    Mutation(
        name="model-sql-bypass",
        path="ask/rerank.py",
        before="allowed = set(original)",
        after="allowed = set(ranking.ordered_ids)",
        case="tests/ask/test_mutation_boundaries.py::test_model_sql_cannot_cross_candidate_id_boundary",
        runner="pytest",
    ),
    Mutation(
        name="unanswerable-guessed-answer",
        path="core/ask_models.py",
        before=(
            "if self.sql is not None or self.result is not None or self.metric_card is not None:"
        ),
        after="if False:",
        case=(
            "tests/ask/test_mutation_boundaries.py::"
            "test_unanswerable_cannot_publish_a_guessed_numeric_answer"
        ),
        runner="pytest",
    ),
)
