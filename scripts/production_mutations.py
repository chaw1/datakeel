# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Mutation anchors for immutable annotation history and database-exclusive assignments."""

from scripts.mutation_models import Mutation

PRODUCTION_MUTATIONS = (
    Mutation(
        name="production-revision-append-only",
        path="storage/production_rows.py",
        before='for table in ("production_revisions", "production_reviews"):',
        after='for table in ("production_reviews",):',
        case=(
            "tests/storage/test_production_workflow.py::"
            "test_revision_database_rejects_update_and_delete[UPDATE]"
        ),
        runner="pytest",
    ),
    Mutation(
        name="production-exclusive-assignment",
        path="storage/production_rows.py",
        before='"stage",\n            unique=True,',
        after='"stage",\n            unique=False,',
        case=(
            "tests/storage/test_production_workflow.py::"
            "test_database_enforces_one_active_assignment_per_task_stage"
        ),
        runner="pytest",
    ),
    Mutation(
        name="production-revision-optimistic-cas",
        path="storage/production_revisions.py",
        before="ProductionTaskRow.latest_revision_id == params.previous_revision_id,",
        after="ProductionTaskRow.id == task.id,",
        case=(
            "tests/storage/test_production_workflow.py::"
            "test_atomic_revision_compare_and_swap_blocks_stale_previous_pointer"
        ),
        runner="pytest",
    ),
    Mutation(
        name="production-stage-claim-authority",
        path="storage/production_assignments.py",
        before='if "*" not in scopes and required not in scopes:',
        after="if False:",
        case=(
            "tests/actions/test_production_workflow_actions.py::"
            "test_reviewer_claim_capability_does_not_grant_annotation_writes"
        ),
        runner="pytest",
    ),
    Mutation(
        name="production-upgrade-retains-personal-owner",
        path="storage/production_projects.py",
        before='if project.workflow_tier == "personal" and upgraded.workflow_tier != "personal":',
        after="if False:",
        case=(
            "tests/api/test_production_flows.py::"
            "test_http_personal_upgrade_resumes_author_then_reviews_and_finalizes[submit]"
        ),
        runner="pytest",
    ),
)
