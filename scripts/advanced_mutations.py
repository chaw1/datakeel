# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Delegation, leak detection and memory regression mutations."""

from scripts.mutation_models import Mutation

ADVANCED_MUTATIONS = (
    Mutation(
        name="mcp-control-tools-denied",
        path="ontology/tooling.py",
        before='    if name in CONTROL_TOOLS and entry == "mcp":',
        after="    if False:",
        case=(
            "tests/mcp/test_server.py::"
            "test_server_exposes_no_approval_or_execution_tool_and_refuses_them"
        ),
        runner="pytest",
    ),
    Mutation(
        name="canary-output-guard",
        path="core/canary.py",
        before="return any(is_leak(canary, text) for text in texts)",
        after="return False",
        case="tests/runtime/test_canary.py::test_canary_guard_cannot_be_disabled",
        runner="pytest",
    ),
    Mutation(
        name="delegation-depth",
        path="delegation/policy.py",
        before="if parent.depth >= limits.delegation_max_depth:",
        after="if False:",
        case="tests/delegation/test_execution.py::test_nested_delegation_cannot_exceed_depth",
        runner="pytest",
    ),
    Mutation(
        name="delegation-scope",
        path="delegation/policy.py",
        before='return scope is None or name in scope or name == "tool_search"',
        after="return True",
        case="tests/delegation/test_execution.py::test_child_cannot_call_outside_scope",
        runner="pytest",
    ),
    Mutation(
        name="memory-hard-delete",
        path="storage/memory_store.py",
        before="            session.delete(rows[memory_id])",
        after="            pass",
        case=(
            "tests/memory/test_deletion.py::"
            "test_delete_memory_when_retrieved_excludes_it_from_new_conversation"
        ),
        runner="pytest",
    ),
    Mutation(
        name="memory-turn-reinforcement",
        path="storage/memory_store.py",
        before="if _used_in_turn(session, scope, identifier):",
        after="if False:",
        case=(
            "tests/memory/test_turn_reinforcement.py::"
            "test_memory_when_three_model_calls_share_question_strengthens_once"
        ),
        runner="pytest",
    ),
)
