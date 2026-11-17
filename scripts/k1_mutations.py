# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Declaration, independent authorization and generated lifecycle regression anchors."""

from scripts.mutation_models import Mutation

_CASE = "tests/actions/test_declarations.py::"
K1_MUTATIONS = (
    Mutation(
        name="k1-frozen-declaration",
        path="actions/declarations.py",
        before="class ActionDeclaration(BoundaryModel):",
        after="class ActionDeclaration(BoundaryModel, frozen=False):",
        case=_CASE + "test_declaration_models_reject_extra_and_mutation",
        runner="pytest",
    ),
    Mutation(
        name="k1-closed-authorization",
        path="actions/declarations.py",
        before="class AuthorizationPolicy(BoundaryModel):",
        after='class AuthorizationPolicy(BoundaryModel, extra="allow"):',
        case=_CASE + "test_declaration_models_reject_extra_and_mutation",
        runner="pytest",
    ),
    Mutation(
        name="k1-deferred-failure-close",
        path="action_store/lifecycle.py",
        before='row.status = "FAILED" if error else "SUCCEEDED"',
        after='row.status = "SUCCEEDED"',
        case="tests/actions/test_declaration_completion.py::test_deferred_work_observes_commit_and_closes_one_attributed_run[True]",
        runner="pytest",
    ),
    Mutation(
        name="k1-resource-rollback",
        path="storage/action_execution.py",
        before="rollback(db, plan, result, attempted=attempted)",
        after="pass",
        case="tests/actions/test_declaration_completion.py::test_execute_failure_releases_declared_external_resource_before_failure_receipt",
        runner="pytest",
    ),
    Mutation(
        name="k1-generated-frontend",
        path="scripts/export_action_declarations.py",
        before="dict(value.phrases)",
        after="dict(value.legacy_examples)",
        case="tests/actions/test_declaration_export.py::test_frontend_export_uses_declared_phrases",
        runner="pytest",
        source_root="repository",
    ),
    Mutation(
        name="k1-duplicate-owner",
        path="actions/file_declarations.py",
        before="if len(result) != len(DECLARATIONS):",
        after="if False:",
        case=_CASE + "test_startup_rejects_duplicate_owner",
        runner="pytest",
    ),
    Mutation(
        name="k1-owner-projection",
        path="actions/ir.py",
        before='"legacy_projection": declaration is None,',
        after='"legacy_projection": True,',
        case=_CASE + "test_ir_keeps_all_owners_in_original_policy_order",
        runner="pytest",
    ),
    Mutation(
        name="k1-generated-effects",
        path="actions/ir.py",
        before='if item.semantics == "structured"',
        after="if False",
        case=_CASE + "test_ir_keeps_all_owners_in_original_policy_order",
        runner="pytest",
    ),
    Mutation(
        name="k1-authorization-independent",
        path="actions/authorization.json",
        before='"split_packages": {\n    "human_only": true',
        after='"split_packages": {\n    "human_only": false',
        case=_CASE + "test_language_deletion_cannot_enable_production_execution",
        runner="pytest",
    ),
    Mutation(
        name="k1-authorization-missing",
        path="actions/authorization.py",
        before="raise AuthorizationError(msg)",
        after="return AuthorizationPolicy()",
        case=_CASE + "test_authorization_deletion_denies_both_entry_guards",
        runner="pytest",
    ),
    Mutation(
        name="k1-dynamic-floor",
        path="action_store/lifecycle.py",
        before='"reversible": prior.reversible and frame.reversible,',
        after='"reversible": frame.reversible,',
        case=_CASE + "test_dynamic_approval_cannot_be_relaxed_by_a_later_hook",
        runner="pytest",
    ),
    Mutation(
        name="k1-generated-executor",
        path="storage/action_operations.py",
        before="if plan.action_type in active_declarations():",
        after="if False:",
        case=_CASE + "test_generated_handler_is_the_actual_file_state_owner",
        runner="pytest",
    ),
)
