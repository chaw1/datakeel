# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Mutation anchors for server authority, local compatibility and signer ceilings."""

from scripts.mutation_models import Mutation

IDENTITY_MUTATIONS = (
    Mutation(
        name="identity-zero-user-compatibility",
        path="storage/identity_authorization.py",
        before='scopes=("*",), zero_users=True',
        after="scopes=(), zero_users=False",
        case="tests/actions/test_identity_actions.py::test_zero_users_preserve_all_scopes_and_callers_can_only_narrow",
        runner="pytest",
    ),
    Mutation(
        name="identity-approver-grant-ceiling",
        path="storage/identity_authorization.py",
        before='if "*" not in current.scopes and not set(scopes).issubset(current.scopes):',
        after="if False:",
        case="tests/actions/test_identity_actions.py::test_approver_cannot_grant_scopes_they_do_not_have",
        runner="pytest",
    ),
    Mutation(
        name="identity-execution-grant-recheck",
        path="storage/action_approvals.py",
        before="    require_role_grant(session, plan, approval.actor)",
        after="    # Deliberately omit the current signer grant check.",
        case="tests/actions/test_identity_actions.py::test_role_grant_rechecked_when_signer_loses_scope_before_execution",
        runner="pytest",
    ),
    Mutation(
        name="identity-legacy-http-write-guard",
        path="api/identity_access.py",
        before="if current.zero_users:\n            return",
        after="if True:\n            return",
        case="tests/api/test_identity_access.py::test_zero_user_http_behavior_and_registered_read_post_remain_available",
        runner="pytest",
    ),
    Mutation(
        name="identity-runtime-actor-binding",
        path="storage/identity_sessions.py",
        before='return row.actor if row is not None else "local"',
        after='return "local"',
        case="tests/api/test_identity_access.py::test_agent_read_session_cannot_borrow_local_administrator_for_writes",
        runner="pytest",
    ),
    Mutation(
        name="identity-history-grant-caller",
        path="storage/data_asset_context.py",
        before="_caller(session_actor(db, conversation_id))",
        after='_caller("local")',
        case="tests/assets/test_identity_context.py::test_history_projection_and_cached_replay_use_session_actor_grants",
        runner="pytest",
    ),
    Mutation(
        name="identity-model-memory-caller",
        path="agent/metering.py",
        before="actor=session_actor(self.db, self.conversation_id),",
        after='actor="local",',
        case="tests/assets/test_identity_context.py::test_named_model_and_http_memory_reads_do_not_borrow_local_grants",
        runner="pytest",
    ),
    Mutation(
        name="identity-memory-write-scope",
        path="storage/memory_store.py",
        before='if "*" not in current.scopes and scope not in current.scopes:',
        after="if False:",
        case="tests/memory/test_identity_write.py::test_registered_unknown_and_acceptance_cannot_write_memory_via_agent",
        runner="pytest",
    ),
)
