# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Native access regressions kill expiry, scope, revocation and cache bypasses."""

from scripts.mutation_models import Mutation

_MATRIX = "tests/assets/test_entry_guards.py::test_all_native_entries_enforce_persistent_grants"

DATA_ASSET_MUTATIONS = (
    Mutation(
        name="asset-missing-grant",
        path="storage/data_asset_access.py",
        before='if asset.definition.classification in {"request", "restricted"} and grant is None:',
        after="if False:",
        case=f"{_MATRIX}[none-request]",
        runner="pytest",
    ),
    Mutation(
        name="asset-expiry",
        path="storage/data_asset_access.py",
        before="and grant.created_at <= now < grant.expires_at",
        after="and True",
        case=f"{_MATRIX}[expired-request]",
        runner="pytest",
    ),
    Mutation(
        name="asset-revocation",
        path="storage/data_asset_access.py",
        before="and grant.revoked_at is None",
        after="and True",
        case=f"{_MATRIX}[revoked-restricted]",
        runner="pytest",
    ),
    Mutation(
        name="asset-scope",
        path="storage/data_asset_access.py",
        before="and context.scope in grant.scopes",
        after="and True",
        case=f"{_MATRIX}[wrong_scope-restricted]",
        runner="pytest",
    ),
    Mutation(
        name="asset-cache-replay",
        path="ontology/tooling.py",
        before='elif previous.name in PARAMETER_MODELS and previous.status == "SUCCEEDED":',
        after="elif False:",
        case="tests/assets/test_replay_guards.py::test_revoked_answer_and_tool_replays_are_rechecked",
        runner="pytest",
    ),
    Mutation(
        name="asset-plan-manifest",
        path="storage/action_access.py",
        before="if not plan.manifest.objects:",
        after="if True:",
        case=(
            "tests/actions/test_asset_plan_access.py::"
            "test_action_preparation_enforces_source_policy_in_every_entry[none]"
        ),
        runner="pytest",
    ),
    Mutation(
        name="asset-agent-message-replay",
        path="agent/service.py",
        before="        require_agent_history(db, conversation_id)",
        after="        pass",
        case=(
            "tests/assets/test_agent_history_reads.py::"
            "test_lost_grants_filter_http_history_and_memories_and_reject_cached_streams[revoked]"
        ),
        runner="pytest",
    ),
    Mutation(
        name="asset-version-producer",
        path="storage/data_asset_native.py",
        before='if ref.asset_type == "dataset" and ref.version is not None:',
        after="if False:",
        case=(
            "tests/assets/test_data_asset_versions.py::"
            "test_controlled_derived_version_file_requires_its_protected_source_grant"
        ),
        runner="pytest",
    ),
)
