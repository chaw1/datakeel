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
        before="if not sources:",
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
    Mutation(
        name="asset-entity-version",
        path="storage/data_asset_native.py",
        before='if ref.asset_type == "kg_entity" and ref.version is not None:',
        after="if False:",
        case=(
            "tests/assets/test_image_relation_guard.py::"
            "test_entity_and_revision_refs_when_dataset_protected_resolve_to_dataset"
        ),
        runner="pytest",
    ),
    Mutation(
        name="asset-content-revision",
        path="storage/data_asset_native.py",
        before=(
            "pinned = ref.version is not None"
            " and _version_dataset(session, ref.version) is not None"
        ),
        after="pinned = ref.version is not None",
        case=(
            "tests/assets/test_image_relation_guard.py::"
            "test_entity_and_revision_refs_when_dataset_protected_resolve_to_dataset"
        ),
        runner="pytest",
    ),
    Mutation(
        name="asset-relaxation-approval",
        path="storage/action_planning.py",
        before="        and not relaxes_asset_access(session, params)\n",
        after="",
        case=(
            "tests/assets/test_asset_relaxation.py::"
            "test_agent_relaxing_protected_asset_requires_human_approval[public-restricted]"
        ),
        runner="pytest",
    ),
    Mutation(
        name="asset-lineage-content",
        path="storage/lineage_service.py",
        before="authorize_query(db, refs, access)",
        after="None",
        case=(
            "tests/assets/test_http_graph_reads.py::"
            "test_graph_runs_and_lineage_when_protected_hide_extracted_names"
        ),
        runner="pytest",
    ),
    Mutation(
        name="asset-dataset-report",
        path="api/routes/governance.py",
        before=(
            "    # Quality findings and reports describe dataset files, "
            "so they share the query guard.\n"
        ),
        after="    return\n",
        case=f"{_MATRIX}[none-restricted]",
        runner="pytest",
    ),
    Mutation(
        name="asset-tool-decision",
        path="storage/data_asset_review.py",
        before=(
            "if action_type == DECISION_ACTION and access is not None "
            "and access.entry in _TOOL_ENTRIES:"
        ),
        after="if False:",
        case=(
            "tests/assets/test_application_review.py::"
            "test_tools_cannot_prepare_approve_or_execute_application_decisions[mcp]"
        ),
        runner="pytest",
    ),
    Mutation(
        name="asset-self-review",
        path="storage/data_asset_review.py",
        before="if same_identity(application.applicant, reviewer):",
        after="if False:",
        case=(
            "tests/assets/test_application_review.py::"
            "test_applicant_cannot_review_own_application_even_with_self_reported_identity"
            "[approved-local]"
        ),
        runner="pytest",
    ),
    Mutation(
        name="asset-self-review-identity",
        path="storage/data_asset_review.py",
        before="return left.strip().casefold() == right.strip().casefold()",
        after="return left == right",
        case=(
            "tests/assets/test_application_review.py::"
            "test_applicant_cannot_review_own_application_even_with_self_reported_identity"
            "[approved- LOCAL ]"
        ),
        runner="pytest",
    ),
    Mutation(
        name="asset-skip-entries",
        path="storage/data_asset_access.py",
        before="        if matched:\n",
        after="        if False:\n",
        case=(
            "tests/assets/test_listing_skips.py::"
            "test_list_tools_skip_protected_entries_and_name_them_by_id[agent]"
        ),
        runner="pytest",
    ),
    Mutation(
        name="asset-skip-export",
        path="storage/lineage_service.py",
        before="        events = [event for event in events if event.event_id not in hidden]\n",
        after="        pass\n",
        case=(
            "tests/assets/test_listing_skips.py::"
            "test_openlineage_export_skips_protected_events_and_reports_them_in_headers"
        ),
        runner="pytest",
    ),
)
