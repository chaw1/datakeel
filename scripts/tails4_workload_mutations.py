# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Mutation anchors for open-work load limits and rework handover between annotators."""

from scripts.mutation_models import Mutation

_LOAD = "tests/actions/test_production_open_load.py::"
_HANDOVER = "tests/actions/test_production_rework_handover.py::"

WORKLOAD_MUTATIONS = (
    Mutation(
        name="workload-open-load-excludes-submitted",
        path="storage/production_dispatch_rules.py",
        before="ProductionTaskRow.state.in_(LEASED_STATES[stage]),",
        after="ProductionTaskRow.state.is_not(None),",
        case=_LOAD + "test_submitted_work_frees_the_limit_and_returned_rework_counts_again",
        runner="pytest",
    ),
    Mutation(
        name="workload-picker-counts-open-work",
        path="storage/production_dispatch_rules.py",
        before="ProductionTaskRow.state.in_(LEASED_STATES[stage]),",
        after="ProductionTaskRow.state.is_not(None),",
        case=_LOAD + "test_picker_preview_and_skill_workload_count_the_same_open_work",
        runner="pytest",
    ),
    Mutation(
        name="workload-dispatch-limit-not-above-project",
        path="storage/production_dispatch_rules.py",
        before="if override is not None and setting is not None and override > setting:",
        after="if False:",
        case=_LOAD + "test_a_dispatch_limit_above_the_project_setting_is_refused_before_signing",
        runner="pytest",
    ),
    Mutation(
        name="workload-prepare-checks-dispatch-limit",
        path="storage/production_dispatch_plans.py",
        before="    if tasks:\n        require_dispatch_limit(",
        after="    if not tasks:\n        require_dispatch_limit(",
        case=_LOAD + "test_a_dispatch_limit_above_the_project_setting_is_refused_before_signing",
        runner="pytest",
    ),
    Mutation(
        name="workload-named-dispatch-honours-lower-limit",
        path="storage/production_assignments.py",
        before="session, project, params.actor, params.stage, len(tasks), params.max_active_tasks",
        after="session, project, params.actor, params.stage, len(tasks)",
        case=_LOAD + "test_a_lower_dispatch_limit_binds_named_and_skill_dispatch",
        runner="pytest",
    ),
    Mutation(
        name="rework-named-handover-allowed",
        path="storage/production_assignments.py",
        before='if handover is not None and source not in {"assign", "skill"}:',
        after="if handover is not None:",
        case=_HANDOVER + "test_reclaimed_rework_is_handed_over_by_name_and_the_plan_says_so[team]",
        runner="pytest",
    ),
    Mutation(
        name="rework-handover-recorded-on-assignment",
        path="storage/production_assignments.py",
        before="        transferred_from=handover,\n",
        after="",
        case=_HANDOVER + "test_reclaimed_rework_is_handed_over_by_name_and_the_plan_says_so[team]",
        runner="pytest",
    ),
    Mutation(
        name="rework-plan-states-handover",
        path="storage/production_dispatch_plans.py",
        before=(
            "transfers = rework_transfers(tasks, params.actor) if named and params.actor else ()"
        ),
        after="transfers = params.transfers",
        case=_HANDOVER + "test_reclaimed_rework_is_handed_over_by_name_and_the_plan_says_so[team]",
        runner="pytest",
    ),
    Mutation(
        name="rework-execution-rechecks-handover",
        path="storage/production_assignments.py",
        before=(
            'if params.stage == "annotation" and rework_transfers(tasks, params.actor) '
            "!= params.transfers:"
        ),
        after="if False:",
        case=_HANDOVER + "test_a_plan_whose_handover_changed_is_refused",
        runner="pytest",
    ),
    Mutation(
        name="rework-skill-keeps-original-in-service",
        path="storage/production_dispatch.py",
        before="if task.round > 0 and original is not None and in_service(session, original):",
        after="if task.round > 0 and original is not None and False:",
        case=_HANDOVER + "test_skill_dispatch_returns_rework_to_an_original_annotator_in_service",
        runner="pytest",
    ),
    Mutation(
        name="rework-skill-hands-over-after-deactivation",
        path="storage/production_dispatch.py",
        before="if task.round > 0 and original is not None and in_service(session, original):",
        after="if task.round > 0 and original is not None:",
        case=_HANDOVER
        + "test_skill_dispatch_hands_rework_over_once_the_original_annotator_is_deactivated",
        runner="pytest",
    ),
    Mutation(
        name="rework-in-service-requires-active-status",
        path="storage/production_dispatch_rules.py",
        before='return row is not None and User.model_validate(row.payload).status == "active"',
        after="return row is not None",
        case=_HANDOVER
        + "test_skill_dispatch_hands_rework_over_once_the_original_annotator_is_deactivated",
        runner="pytest",
    ),
    Mutation(
        name="rework-preview-names-handover",
        path="storage/production_dispatch.py",
        before='                if request.stage == "annotation"\n                else None,',
        after="                if False\n                else None,",
        case=_HANDOVER
        + "test_skill_dispatch_hands_rework_over_once_the_original_annotator_is_deactivated",
        runner="pytest",
    ),
)
