# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Anchors for checking every self-claim rule before a confirmation card is made."""

from scripts.mutation_models import Mutation

_T = "tests/intents/test_claim_rules.py::"
_M = "tests/intents/test_claim_chain_matrix.py::test_claim_dispatch_chain_matrix"


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
    _anchor(
        "earlier-claims-consume-capacity",
        (
            "    load = open_load(db, project.id, stage, person) + target.load_delta",
            "    load = open_load(db, project.id, stage, person)",
        ),
        "test_two_claims_at_limit_one_are_refused_before_the_second_card",
    ),
    _anchor(
        "earlier-claims-consume-free-tasks",
        ("    free = free[target.prior_claims :]", "    free = free"),
        "test_an_earlier_claim_consumes_the_last_free_task",
    ),
    Mutation(
        name="claim-upgrade-preserves-effective-strategy",
        path="intents/claim_effects.py",
        before="            self.project = _configure(self.project, step)",
        after="            self.project = self.project",
        case=_T + "test_upgrade_preserves_assign_only_strategy_and_a_legal_upgrade_executes",
        runner="pytest",
    ),
    Mutation(
        name="assign-uses-the-same-effective-load",
        path="intents/preconditions.py",
        before=(
            '    projected = step.action in {"claim_task", "assign_tasks"} '
            "and target.project is not None"
        ),
        after='    projected = step.action == "claim_task" and target.project is not None',
        case=_M + "[claim-assign-over]",
        runner="pytest",
    ),
    Mutation(
        name="release-restores-one-load-slot",
        path="intents/claim_effects.py",
        before=(
            "            elif holders.get(task) == person and task not in self.released:\n"
            "                self.load_delta -= 1"
        ),
        after=("            elif False:\n                self.load_delta -= 1"),
        case=_M + "[release-claim-claim-over]",
        runner="pytest",
    ),
    Mutation(
        name="release-returns-the-task-to-the-free-queue",
        path="intents/claim_effects.py",
        before="        self.released.update(tasks)",
        after="        self.released.clear()",
        case=_M + "[release-only-free]",
        runner="pytest",
    ),
)
