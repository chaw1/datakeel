# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""FIX3 anchors for groups said any way and for what execution would refuse.

They lock unwrapped and last-N task groups, review-stage assignment, the question when
protection empties a group, reviews of tasks not waiting for review, release tags that are
taken, pre-label models that cannot draw boxes, and role cards in words.
"""

from scripts.mutation_models import Mutation

_LIMITS = "tests/intents/test_fix3_limits.py::"
LIMITS_MUTATIONS = (
    Mutation(
        name="fix3-unwrapped-conditions-are-a-task-group",
        path="intents/group_fill.py",
        before="    if isinstance(value, dict) and value and set(value) <= SELECTOR_KEYS:",
        after="    if False:",
        case=_LIMITS + "test_a_group_left_unwrapped_or_counted_from_the_end_is_that_group",
        runner="pytest",
    ),
    Mutation(
        name="fix3-the-last-n-tasks-are-counted-from-the-end",
        path="intents/task_scope.py",
        before="    return list(range(max(total - last, 0) + 1, total + 1)) if last else None",
        after="    return None",
        case=_LIMITS + "test_a_group_left_unwrapped_or_counted_from_the_end_is_that_group",
        runner="pytest",
    ),
    Mutation(
        name="fix3-review-assignment-takes-tasks-waiting-for-review",
        path="intents/task_scope.py",
        before='        return task.state in (REVIEW_STATES if stage == "review" else OPEN_STATES)',
        after="        return task.state in OPEN_STATES",
        case=_LIMITS + "test_assigning_for_review_takes_only_tasks_waiting_for_review",
        runner="pytest",
    ),
    Mutation(
        name="fix3-review-stage-only-counts-review-holds",
        path="intents/task_scope.py",
        before='    held = task.holder is not None and stage in {"annotation", task.stage}',
        after="    held = task.holder is not None",
        case=_LIMITS + "test_assigning_for_review_takes_only_tasks_waiting_for_review",
        runner="pytest",
    ),
    Mutation(
        name="fix3-a-protected-group-is-asked-about",
        path="intents/group_fill.py",
        before="        if left_out:\n            return include_question(",
        after="        if False:\n            return include_question(",
        case=_LIMITS + "test_a_group_that_protection_empties_is_asked_about_not_answered",
        runner="pytest",
    ),
    Mutation(
        name="fix3-a-picked-include-unlocks-the-group",
        path="intents/task_scope.py",
        before='list(raw.split(",")) if isinstance(raw, str) else []',
        after="[]",
        case=_LIMITS + "test_a_group_that_protection_empties_is_asked_about_not_answered",
        runner="pytest",
    ),
    Mutation(
        name="fix3-review-needs-a-task-waiting-for-review",
        path="intents/impossible.py",
        before='    "review_task": _review,\n',
        after="",
        case=_LIMITS + "test_a_review_of_a_task_not_waiting_for_review_says_why",
        runner="pytest",
    ),
    Mutation(
        name="fix3-p5-a-published-release-tag-is-taken",
        path="intents/duplicates.py",
        before='    if found is not None or step.action != "publish_release":',
        after="    if True:",
        case=_LIMITS + "test_a_release_tag_the_dataset_has_is_never_published_again",
        runner="pytest",
    ),
    Mutation(
        name="fix3-p5-a-model-that-cannot-pre-label-is-asked",
        path="intents/validate.py",
        before=" or model_question(db, step, language)",
        after="",
        case=_LIMITS
        + "test_a_pre_label_model_that_cannot_draw_boxes_is_said_and_box_models_offered",
        runner="pytest",
    ),
    Mutation(
        name="fix3-p4-said-words-never-hide-internal-names",
        path="intents/public_text.py",
        before='rest = re.sub(whole, " ", rest) if name.isascii() else rest.replace(name, " ")',
        after='rest = rest.replace(name, " ")',
        case=_LIMITS + "test_role_cards_name_actions_and_permissions_in_words",
        runner="pytest",
    ),
    Mutation(
        name="fix3-p4-role-scopes-in-words",
        path="intents/describe.py",
        before='    "scopes": _scopes,\n',
        after="",
        case=_LIMITS + "test_role_cards_name_actions_and_permissions_in_words",
        runner="pytest",
    ),
)
