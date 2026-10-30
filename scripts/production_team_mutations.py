# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Mutation anchors for team leases, the reaper, separation, acceptance and lock discipline.

The full mutation run uses SQLite. The two lock anchors therefore remove the step that every
database shares (the declared up-front table lock, the per-person serialization call); their
PostgreSQL behavior tests turn red under the same changes.
"""

from scripts.mutation_models import Mutation

_LEASES = "tests/storage/test_production_leases.py::"
_SEPARATION = "tests/storage/test_production_separation.py::"
_DISPATCH = "tests/actions/test_production_team_dispatch.py::"
_ACCEPTANCE = "tests/actions/test_production_team_acceptance.py::"
_LOCK_ORDER = "tests/actions/test_production_lock_order.py::"
_LOAD_LOCKS = "tests/actions/test_production_load_locks.py::"
_FREEZE = "tests/actions/test_production_plan_freeze.py::"

PRODUCTION_TEAM_MUTATIONS = (
    Mutation(
        name="production-team-lease-expiry",
        path="storage/production_leases.py",
        before=(
            "return row.lease_expires_at is not None and row.lease_expires_at <= now.timestamp()"
        ),
        after="return False",
        case=_LEASES + "test_expired_lease_rejects_save_submit_and_heartbeat_explicitly",
        runner="pytest",
    ),
    Mutation(
        name="production-team-lease-deadline-boundary",
        path="storage/production_leases.py",
        before=(
            "return row.lease_expires_at is not None and row.lease_expires_at <= now.timestamp()"
        ),
        after="return row.lease_expires_at is not None and row.lease_expires_at < now.timestamp()",
        case=_LEASES + "test_lease_expires_exactly_at_its_deadline",
        runner="pytest",
    ),
    Mutation(
        name="production-team-reaper-releases-once",
        path="storage/production_reaper.py",
        before="if row is None or not row.active or not lease_expired(row, now):",
        after="if row is None or not lease_expired(row, now):",
        case=_LEASES + "test_stale_reaper_candidate_is_released_only_once",
        runner="pytest",
    ),
    Mutation(
        name="production-team-reaper-rereads-renewal",
        path="storage/production_reaper.py",
        before="if row is None or not row.active or not lease_expired(row, now):",
        after="if row is None or not row.active:",
        case=_LEASES + "test_lease_renewed_after_listing_is_not_released",
        runner="pytest",
    ),
    Mutation(
        name="production-team-review-separation",
        path="storage/production_separation.py",
        before='if project.workflow_tier == "team" and actor in annotators(session, task):',
        after="if False:",
        case=_SEPARATION + "test_team_annotator_cannot_claim_be_assigned_or_review_own_task",
        runner="pytest",
    ),
    Mutation(
        name="production-team-review-queue-separation",
        path="storage/production_assignments.py",
        before="query = exclude_own_work(query, actor)",
        after="query = query",
        case=_SEPARATION + "test_role_change_does_not_lift_separation",
        runner="pytest",
    ),
    Mutation(
        name="production-team-skill-level-filter",
        path="storage/production_dispatch_rules.py",
        before="return skill_level(session, actor, requirement) >= requirement.min_level",
        after="return skill_level(session, actor, requirement) > 0",
        case=_DISPATCH + "test_skill_level_filter_admits_the_exact_minimum_and_rejects_below",
        runner="pytest",
    ),
    Mutation(
        name="production-team-whole-package-return",
        path="storage/production_acceptance.py",
        before="        for task in tasks:\n            return_for_rework(session, project, task)",
        after=(
            "        for task in (item for item in tasks if item.id in sampling.task_ids):\n"
            "            return_for_rework(session, project, task)"
        ),
        case=_ACCEPTANCE + "test_rejection_returns_every_package_task_for_one_more_round",
        runner="pytest",
    ),
    Mutation(
        name="production-team-table-locks-before-rows",
        path="storage/action_locks.py",
        before='        return ("lineage_events",), "ROW EXCLUSIVE"',
        after='        return (), "ROW EXCLUSIVE"',
        case=_LOCK_ORDER
        + "test_single_task_actions_lock_every_predicate_table_they_write_up_front",
        runner="pytest",
    ),
    Mutation(
        name="production-team-claim-serializes-person-load",
        path="storage/production_dispatch_rules.py",
        before=(
            "    lock_people(session, project.id, (actor,))\n"
            "    require_capacity(session, project, actor, stage)"
        ),
        after="    require_capacity(session, project, actor, stage)",
        case=_LOAD_LOCKS + "test_concurrent_claims_by_one_person_stop_exactly_at_the_limit",
        runner="pytest",
    ),
    Mutation(
        name="production-team-plan-freezes-holders-only",
        path="storage/production_action_state.py",
        before="if isinstance(params, AssignTasksParams | RevokeAssignmentParams):",
        after="if False:",
        case=_FREEZE + "test_revoke_plan_survives_holder_saves_and_heartbeats",
        runner="pytest",
    ),
    Mutation(
        name="production-team-plan-freezes-state",
        path="storage/production_action_state.py",
        before='{"task_id": task.id, "state": task.state, "round": task.round, "holders": holders}',
        after='{"task_id": task.id, "round": task.round, "holders": holders}',
        case=_FREEZE + "test_revoke_plan_is_rejected_once_the_holder_submits",
        runner="pytest",
    ),
)
