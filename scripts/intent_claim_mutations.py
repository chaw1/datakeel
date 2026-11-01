# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Anchors for checking every self-claim rule before a confirmation card is made."""

from scripts.mutation_models import Mutation

_T = "tests/intents/test_claim_rules.py::"


def _anchor(name: str, change: tuple[str, str], case: str) -> Mutation:
    before, after = change
    return Mutation(
        name=f"claim-{name}",
        path="intents/preconditions.py",
        before=before,
        after=after,
        case=_T + case,
        runner="pytest",
    )


CLAIM_MUTATIONS = (
    _anchor(
        "review-skips-past-and-current-annotators",
        (
            '    if project.workflow_tier == "team" and target.stage == "review":',
            "    if False:",
        ),
        "test_review_claims_skip_everyone_who_annotated_even_after_a_handover",
    ),
    _anchor(
        "team-open-work-limit",
        (
            '    "claim_task": ("finalized", "claim_strategy", "capacity", "free_task"),',
            '    "claim_task": ("finalized", "claim_strategy", "free_task"),',
        ),
        "test_a_team_claim_at_the_person_limit_is_refused_but_another_person_can_claim",
    ),
    _anchor(
        "manager-assignment-only",
        (
            '        or project.dispatch_strategy != "assign"',
            '        or project.dispatch_strategy != "claim"',
        ),
        "test_manager_assigned_projects_do_not_offer_self_claim",
    ),
)
