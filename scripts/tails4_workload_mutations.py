# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Mutation anchors for open-work load limits."""

from scripts.mutation_models import Mutation

_LOAD = "tests/actions/test_production_open_load.py::"

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
)
