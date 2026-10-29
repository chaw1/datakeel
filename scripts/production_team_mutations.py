# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Mutation anchors for team leases, the single-release reaper, separation and acceptance."""

from scripts.mutation_models import Mutation

_LEASES = "tests/storage/test_production_leases.py::"
_SEPARATION = "tests/storage/test_production_separation.py::"
_DISPATCH = "tests/actions/test_production_team_dispatch.py::"
_ACCEPTANCE = "tests/actions/test_production_team_acceptance.py::"

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
)
