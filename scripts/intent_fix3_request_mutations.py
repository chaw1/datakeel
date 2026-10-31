# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""FIX3 anchors: one task meant, places in a group, teams as holders, states said first.

Each mutation removes one rule; the named test must fail without it.
"""

from __future__ import annotations

from scripts.mutation_models import Mutation

_REQUESTS = "tests/intents/test_fix3_requests.py::"
_ONE = _REQUESTS + "test_one_task_meant_is_asked_and_only_saved_work_is_handed_in"
_PLACES = _REQUESTS + "test_numbers_in_a_described_group_and_this_package_from_the_page"
_STATES = _REQUESTS + "test_states_the_request_cannot_change_are_said_before_planning"
_FREED = _REQUESTS + "test_a_task_taken_back_earlier_in_the_plan_is_free_for_the_next_step"
_OWNER = "tests/intents/test_fix3_ownership.py::"
_LIMITS = "tests/intents/test_fix3_limits.py::"


def _anchor(name: str, path: str, change: tuple[str, str], case: str) -> Mutation:
    before, after = change
    return Mutation(name=name, path=path, before=before, after=after, case=case, runner="pytest")


REQUEST_MUTATIONS = (
    _anchor(
        "fix3-an-empty-read-group-is-said",
        "intents/resolve.py",
        (
            (
                '            return IntentResult(kind="answer", text=filled.empty_selection or "", '
                "request=text)"
            ),
            '            return IntentResult(kind="answer", text="", request=text)',
        ),
        _ONE,
    ),
    _anchor(
        "fix3-a-read-finds-what-the-person-annotated",
        "intents/group_fill.py",
        ('    return "read" if current.action in TASK_READS else stage', "    return stage"),
        _ONE,
    ),
    _anchor(
        "fix3-one-task-meant-is-asked",
        "intents/group_fill.py",
        (
            '    if len(ids) > 1 and field == "task_id" and says_one(state.text):',
            "    if False:",
        ),
        _ONE,
    ),
    _anchor(
        "fix3-only-saved-open-work-is-handed-in",
        "intents/task_scope.py",
        ("        return task.annotated and task.state in OPEN_STATES", "        return True"),
        _ONE,
    ),
    _anchor(
        "fix3-numbers-outside-a-group-are-places-in-it",
        "intents/task_scope.py",
        (
            (
                "        if not all(n in inside for n in said) and all(n <= len(described) "
                "for n in said):"
            ),
            "        if False:",
        ),
        _PLACES,
    ),
    _anchor(
        "fix3-assigning-leaves-out-handed-in-tasks",
        "intents/task_scope.py",
        (
            "    kept = [task.id for task in unique if task.state in allowed]",
            "    kept = [task.id for task in unique]",
        ),
        _OWNER + "test_places_count_inside_a_named_package_and_from_the_end",
    ),
    _anchor(
        "fix3-this-package-is-the-page-s",
        "intents/group_fill.py",
        (
            '    package = page_package(db, spec.get("package"), state) or (',
            "    package = None or (",
        ),
        _PLACES,
    ),
    _anchor(
        "fix3-a-team-holder-is-its-members",
        "intents/group_fill.py",
        (
            (
                '    team = _members(db, spec.get("holder"), catalog) if isinstance(person, '
                "Clarification) else None"
            ),
            "    team = None",
        ),
        _REQUESTS + "test_a_team_named_as_holder_means_its_members",
    ),
    _anchor(
        "fix3-all-of-someone-s-tasks-include-saved-work",
        "intents/group_fill.py",
        (
            (
                '    if current.action == "revoke_assignment" and holder is not None and '
                "says_whole(state.text):"
            ),
            "    if False:",
        ),
        _LIMITS + "test_a_group_that_protection_empties_is_asked_about_not_answered",
    ),
    _anchor(
        "fix3-reopening-open-work-is-already-so",
        "intents/verify.py",
        ('    if step.action == "reopen_task":\n        return _already_open(db, step)\n', ""),
        _STATES,
    ),
    _anchor(
        "fix3-made-up-scopes-are-dropped",
        "intents/object_edits.py",
        (
            (
                "    scopes = {str(item) for item in said} & known if isinstance(said, list) "
                "else set(held)"
            ),
            "    scopes = {str(item) for item in said} if isinstance(said, list) else set(held)",
        ),
        _STATES,
    ),
    _anchor(
        "fix3-an-unpublished-version-is-asked",
        "intents/validate.py",
        (
            (
                "        or unpublished_question(db, step, [item.action for item in previous], "
                "language)\n"
            ),
            "",
        ),
        _STATES,
    ),
    _anchor(
        "fix3-a-publish-earlier-in-the-plan-publishes-it",
        "intents/duplicates.py",
        (
            '    if step.action != "create_project" or "publish_label_set" in earlier:',
            '    if step.action != "create_project":',
        ),
        _STATES,
    ),
    _anchor(
        "fix3-a-task-taken-back-earlier-is-free",
        "intents/fill.py",
        ("        state.freed.update(freed(filled[-1]))\n", ""),
        _FREED,
    ),
)
