# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Anchors: one task meant, places in a group, teams as holders, states said first.

Each mutation removes one rule; the named test must fail without it.
"""

from __future__ import annotations

from scripts.mutation_models import Mutation

_REQUESTS = "tests/intents/test_task_requests.py::"
_ONE = _REQUESTS + "test_one_task_meant_is_asked_and_only_saved_work_is_handed_in"
_PLACES = _REQUESTS + "test_numbers_in_a_described_group_and_this_package_from_the_page"
_STATES = _REQUESTS + "test_states_the_request_cannot_change_are_said_before_planning"
_FREED = _REQUESTS + "test_a_task_taken_back_earlier_in_the_plan_is_free_for_the_next_step"
_STATE = "tests/intents/test_plan_state.py::"
_FILE = _STATE + "test_a_task_named_by_its_file_is_that_task"
_NARROW = _STATE + "test_numbers_that_are_not_places_narrow_the_described_group"
_FOLLOWS = _STATE + "test_a_version_that_follows_its_label_set_is_not_asked"
_EARLIER = _STATE + "test_an_earlier_step_changes_what_later_steps_may_do"
_THERE = _STATE + "test_adding_a_label_that_is_there_already_changes_nothing"
_OWNER = "tests/intents/test_task_ownership.py::"
_LIMITS = "tests/intents/test_group_limits.py::"


def _anchor(name: str, path: str, change: tuple[str, str], case: str) -> Mutation:
    before, after = change
    return Mutation(name=name, path=path, before=before, after=after, case=case, runner="pytest")


REQUEST_MUTATIONS = (
    _anchor(
        "planning-an-empty-read-group-is-said",
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
        "planning-a-read-finds-what-the-person-annotated",
        "intents/group_fill.py",
        ('    return "read" if current.action in TASK_READS else stage', "    return stage"),
        _ONE,
    ),
    _anchor(
        "planning-one-task-meant-is-asked",
        "intents/group_fill.py",
        (
            '    if len(ids) > 1 and field == "task_id" and says_one(state.text):',
            "    if False:",
        ),
        _ONE,
    ),
    _anchor(
        "planning-only-saved-open-work-is-handed-in",
        "intents/task_scope.py",
        ("        return task.annotated and task.state in OPEN_STATES", "        return True"),
        _ONE,
    ),
    _anchor(
        "planning-numbers-outside-a-group-are-places-in-it",
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
        "planning-assigning-leaves-out-handed-in-tasks",
        "intents/task_scope.py",
        (
            "    kept = [task.id for task in unique if task.state in allowed]",
            "    kept = [task.id for task in unique]",
        ),
        _OWNER + "test_places_count_inside_a_named_package_and_from_the_end",
    ),
    _anchor(
        "planning-this-package-is-the-page-s",
        "intents/group_fill.py",
        (
            '    package = page_package(db, spec.get("package"), state) or (',
            "    package = None or (",
        ),
        _PLACES,
    ),
    _anchor(
        "planning-a-team-holder-is-its-members",
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
        "planning-all-of-someone-s-tasks-include-saved-work",
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
        "planning-reopening-open-work-is-already-so",
        "intents/verify.py",
        ('    if step.action == "reopen_task":\n        return _already_open(db, step)\n', ""),
        _STATES,
    ),
    _anchor(
        "planning-made-up-scopes-are-dropped",
        "intents/object_edits.py",
        (
            "        scopes = (set(named) & known) | {",
            "        scopes = set(named) | {",
        ),
        _STATES,
    ),
    _anchor(
        "planning-an-unpublished-version-is-asked",
        "intents/validate.py",
        (
            (
                "    asked = asked or unpublished_question(db, step, [item.action for item in "
                "previous], language)"
            ),
            "    asked = asked",
        ),
        _STATES,
    ),
    _anchor(
        "planning-a-publish-earlier-in-the-plan-publishes-it",
        "intents/duplicates.py",
        (
            '    if step.action != "create_project" or "publish_label_set" in earlier:',
            '    if step.action != "create_project":',
        ),
        _STATES,
    ),
    _anchor(
        "planning-a-task-taken-back-earlier-is-free",
        "intents/replanning.py",
        ("        if dependent:", "        if False:"),
        _FREED,
    ),
    _anchor(
        "planning-a-task-named-by-its-file-is-that-task",
        "intents/task_files.py",
        (
            '            if name and wanted in {name, name.rsplit(".", 1)[0]}:',
            "            if False:",
        ),
        _FILE,
    ),
    _anchor(
        "planning-a-task-said-only-in-words-is-the-step-s",
        "intents/fill.py",
        ("        said_task(step, params)\n", ""),
        _FILE,
    ),
    _anchor(
        "planning-numbers-that-are-not-places-narrow-the-group",
        "intents/task_scope.py",
        ("        if both and len(both) < len(said):", "        if False:"),
        _NARROW,
    ),
    _anchor(
        "planning-a-version-that-follows-its-label-set-is-not-asked",
        "intents/validate.py",
        ("        and not any(name in FOLLOWS.get(other, ()) for other in missing)\n", ""),
        _FOLLOWS,
    ),
    _anchor(
        "planning-an-earlier-upgrade-lifts-the-personal-rules",
        "intents/replanning.py",
        ("        if dependent:", "        if False:"),
        _EARLIER,
    ),
    _anchor(
        "planning-a-downgrade-is-said",
        "intents/impossible.py",
        ('    "upgrade_project": _upgrade,\n', ""),
        _EARLIER,
    ),
    _anchor(
        "planning-an-account-turned-back-on-takes-work",
        "intents/fill.py",
        ("        reopened(created, filled[-1], user.label if user is not None else None)\n", ""),
        _EARLIER,
    ),
    _anchor(
        "planning-adding-a-label-that-is-there-changes-nothing",
        "intents/edits.py",
        (
            (
                "        if _existing(labels, raw) is None "
                "and (label := _label(raw, taken)) is not None:"
            ),
            "        if (label := _label(raw, taken)) is not None:",
        ),
        _THERE,
    ),
)
