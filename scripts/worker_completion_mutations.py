# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Typed completion routing, terminal attribution and heartbeat fence assertion anchors."""

from scripts.mutation_models import Mutation

_ROUTES = "tests/worker_store/test_completion_routes.py::"
_ADAPTER = "persistence/task_completion.py"
_MISMATCH = _ROUTES + "test_mismatched_or_missing_product_rejected_for_each_route"
_ROUTING = _ROUTES + "test_each_product_routes_once_and_terminal_failure_keeps_attribution"

WORKER_COMPLETION_MUTATIONS = (
    Mutation(
        name="completion-unique-association",
        path=_ADAPTER,
        before="if sum(value is not None for value in associations) > 1",
        after="if sum(value is not None for value in associations) > 3",
        case=_ROUTES + "test_duplicate_and_empty_associations_fail_closed",
        runner="pytest",
    ),
    Mutation(
        name="completion-nonempty-association",
        path=_ADAPTER,
        before='value == "" for value in associations',
        after='value == "never-empty" for value in associations',
        case=_ROUTES + "test_duplicate_and_empty_associations_fail_closed",
        runner="pytest",
    ),
    Mutation(
        name="completion-product-required",
        path=_ADAPTER,
        before="if not matches and not empty_failure:",
        after="if False:",
        case=_MISMATCH,
        runner="pytest",
    ),
    Mutation(
        name="completion-kg-exact-identity",
        path=_ADAPTER,
        before="and payload.run.id == request.kg_run_id",
        after="and True",
        case=_MISMATCH,
        runner="pytest",
    ),
    Mutation(
        name="completion-dq-exact-identity",
        path=_ADAPTER,
        before="and payload.run_id == request.dq_run_id",
        after="and True",
        case=_MISMATCH,
        runner="pytest",
    ),
    Mutation(
        name="completion-datasheet-exact-identity",
        path=_ADAPTER,
        before="and payload.job_id == request.datasheet_job_id",
        after="and True",
        case=_MISMATCH,
        runner="pytest",
    ),
    Mutation(
        name="completion-product-requires-association",
        path=_ADAPTER,
        before="raise ConflictError(msg)\n        discard = bool(request.error)",
        after=(
            'return CompletionResult(operator="pipeline.complete")\n'
            "        discard = bool(request.error)"
        ),
        case=_ROUTES + "test_missing_association_rejects_every_domain_payload",
        runner="pytest",
    ),
    Mutation(
        name="completion-kg-terminal-attribution",
        path=_ADAPTER,
        before='return CompletionResult(operator="kg.complete")',
        after='return CompletionResult(operator="pipeline.complete")',
        case=_ROUTING,
        runner="pytest",
    ),
    Mutation(
        name="completion-dq-terminal-attribution",
        path=_ADAPTER,
        before='return CompletionResult(operator="dq.complete")',
        after='return CompletionResult(operator="pipeline.complete")',
        case=_ROUTING,
        runner="pytest",
    ),
    Mutation(
        name="completion-datasheet-terminal-display",
        path=_ADAPTER,
        before='display_name="Datasheet generation"',
        after='display_name="Pipeline run"',
        case=_ROUTING,
        runner="pytest",
    ),
    Mutation(
        name="completion-pipeline-version-policy",
        path=_ADAPTER,
        before='return CompletionResult(operator="pipeline.complete", publish_version=True)',
        after='return CompletionResult(operator="pipeline.complete", publish_version=False)',
        case=_ROUTING,
        runner="pytest",
    ),
    Mutation(
        name="completion-refreshed-heartbeat-fence",
        path="worker_store/task_queue.py",
        before="if expired_before is not None and (shard.heartbeat_at or 0) >= expired_before:",
        after="if False:",
        case=(
            "tests/worker_store/test_completion_transactions.py::"
            "test_refreshed_heartbeat_blocks_exhaustion_without_entering_completion"
        ),
        runner="pytest",
    ),
)
