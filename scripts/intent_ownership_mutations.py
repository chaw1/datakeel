# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Anchors: whose task, places in a package, names made earlier, edits keep the rest.

Each mutation removes one rule; the named test must fail without it.
"""

from __future__ import annotations

from scripts.mutation_models import Mutation

_OWNER = "tests/intents/test_task_ownership.py::"
_WHOSE = _OWNER + "test_review_and_own_tasks_are_found_by_who_holds_or_handed_them_in"
_PLACES = _OWNER + "test_places_count_inside_a_named_package_and_from_the_end"
_FILES = _OWNER + "test_files_named_without_extension_find_their_dataset_and_list_in_order"
_EDITS = _OWNER + "test_edits_keep_what_the_words_leave_unsaid"
_ROLE = _OWNER + "test_a_role_without_a_project_and_a_team_already_led_so"
_LINEAGE = _OWNER + "test_lineage_is_read_by_name_and_said_in_words"


def _anchor(name: str, path: str, change: tuple[str, str], case: str) -> Mutation:
    before, after = change
    return Mutation(name=name, path=path, before=before, after=after, case=case, runner="pytest")


OWNER_MUTATIONS = (
    _anchor(
        "planning-a-review-group-is-the-review-stage",
        "intents/group_fill.py",
        ('    stage = "review" if current.action == "review_task" else stage\n', ""),
        _WHOSE,
    ),
    _anchor(
        "planning-in-review-a-task-is-also-its-annotator-s",
        "intents/task_scope.py",
        (
            (
                '    own = stage in {"review", "read"} or '
                "(task.holder is None and task.state in OPEN_STATES)"
            ),
            "    own = False",
        ),
        _WHOSE,
    ),
    _anchor(
        "planning-only-handed-in-tasks-are-reviewed",
        "intents/task_scope.py",
        ('    return action != "review_task" or task.state in REVIEW_STATES', "    return True"),
        _WHOSE,
    ),
    _anchor(
        "planning-my-task-is-the-speaker-s-own",
        "intents/fill.py",
        ("        own_task(step.action, params, state.context)\n", ""),
        _WHOSE,
    ),
    _anchor(
        "planning-giving-back-finds-a-hold-in-either-stage",
        "intents/group_fill.py",
        (
            '    either = not current.params.get("stage") and current.action in ANY_STAGE',
            "    either = False",
        ),
        _WHOSE,
    ),
    _anchor(
        "planning-the-stage-of-the-hold-found-is-the-step-s",
        "intents/group_fill.py",
        ('        current.params["stage"] = held.pop()', "        held.pop()"),
        _WHOSE,
    ),
    _anchor(
        "planning-the-speaker-is-you-not-me",
        "intents/group_fill.py",
        ('            named = "你" if state.language == "zh" else "you"', "            pass"),
        _WHOSE,
    ),
    _anchor(
        "planning-a-place-in-a-package-counts-in-the-package",
        "intents/task_scope.py",
        (
            (
                "        return [n if n in inside else inside[n - 1] if n <= len(inside) else 0 "
                "for n in named]"
            ),
            "        return named",
        ),
        _PLACES,
    ),
    _anchor(
        "planning-a-package-is-a-place-not-a-condition",
        "intents/task_scope.py",
        (
            "    if any(key in spec for key in FILTERS):",
            "    if any(key in spec for key in CONDITIONS):",
        ),
        _PLACES,
    ),
    _anchor(
        "planning-second-to-last-is-one-task",
        "intents/group_fill.py",
        ("    spec = from_end(spec, state.text)\n", ""),
        _PLACES,
    ),
    _anchor(
        "planning-a-name-made-earlier-is-not-looked-up",
        "intents/fill.py",
        ("        remember(created, filled[-1], fresh)\n", ""),
        _OWNER + "test_a_name_an_earlier_step_creates_is_used_not_looked_up",
    ),
    _anchor(
        "planning-a-file-stem-names-its-file",
        "intents/selectors.py",
        ("            by_name.setdefault(stem, next(iter(owners)))", "            pass"),
        _FILES,
    ),
    _anchor(
        "planning-named-files-find-their-dataset",
        "intents/group_fill.py",
        ("        dataset = _holding_dataset(db, spec, catalog)", "        dataset = None"),
        _FILES,
    ),
    _anchor(
        "planning-a-bad-dataset-identity-is-the-page-s",
        "intents/fill.py",
        ('        return {**value, "dataset_id": paged}', "        return value"),
        _FILES,
    ),
    _anchor(
        "planning-sample-files-by-name-are-their-ids",
        "intents/fill.py",
        ("        sample_files(params)\n", ""),
        _FILES,
    ),
    _anchor(
        "planning-a-model-edit-keeps-the-rest",
        "intents/object_edits.py",
        (
            '    params["model"] = {**stored, **model, "id": current.id}',
            '    params["model"] = model',
        ),
        _EDITS,
    ),
    _anchor(
        "planning-a-role-edit-keeps-its-permissions",
        "intents/object_edits.py",
        (
            "    scopes = set(held)\n",
            "    scopes = set()\n",
        ),
        _EDITS,
    ),
    _anchor(
        "planning-a-role-without-a-project-is-asked",
        "intents/step_values.py",
        (
            '    bound = bound_projects(db, params) if current.action == "manage_users" else []',
            "    bound = []",
        ),
        _ROLE,
    ),
    _anchor(
        "planning-a-team-already-led-so-is-already-so",
        "intents/verify.py",
        (
            (
                '    if params.get("operation") == "update_team":\n'
                "        return _team_unchanged(db, params)\n"
            ),
            "",
        ),
        _ROLE,
    ),
    _anchor(
        "planning-an-asset-said-by-name-is-read",
        "intents/fill.py",
        ("        return any_asset(value, catalog)", "        return value"),
        _LINEAGE,
    ),
    _anchor(
        "planning-lineage-said-in-words",
        "intents/answers.py",
        ('        "get_lineage": lineage_text,\n', ""),
        _LINEAGE,
    ),
)
