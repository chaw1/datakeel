# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""FIX3 regression anchors for one-sentence planning, one per structural rule P1-P7.

They lock names over the page (P1), one display order (P2), values read from state (P3),
plain outgoing words (P4), new versus existing names (P5), scope-less reads (P6), every
part of a request planned or explained (P7) and the two drafting side fixes (9.4).
"""

from scripts.intent_fix3_limit_mutations import LIMITS_MUTATIONS
from scripts.intent_fix3_owner_mutations import OWNER_MUTATIONS
from scripts.mutation_models import Mutation

_SCOPE = "tests/intents/test_fix3_scope.py::"
_WORDS = "tests/intents/test_fix3_words.py::"
_ACTIONS = "tests/intents/test_fix3_actions.py::"
_PARTS = "tests/intents/test_fix3_parts.py::"

NAMES_AND_ORDER_MUTATIONS = (
    Mutation(
        name="fix3-p1-words-name-the-container-before-the-page",
        path="intents/fill.py",
        before=(
            "    value = named_in_words(field, state, catalog) "
            "or context_value(field, state, catalog)"
        ),
        after="    value = context_value(field, state, catalog)",
        case=_SCOPE + "test_a_project_named_in_the_words_wins_over_the_page",
        runner="pytest",
    ),
    Mutation(
        name="fix3-p1-a-package-fixes-its-project",
        path="intents/fill.py",
        before='    if field == "project_id" and owner is not None and owner.parent:',
        after="    if False:",
        case=_PARTS + "test_a_numbered_package_without_a_project_offers_each_project_s_package",
        runner="pytest",
    ),
    Mutation(
        name="fix3-p1-numbered-package-without-project-is-offered",
        path="intents/group_fill.py",
        before="    if project is None and number:",
        after="    if False:",
        case=_PARTS + "test_a_numbered_package_without_a_project_offers_each_project_s_package",
        runner="pytest",
    ),
    Mutation(
        name="fix3-p1-read-narrowed-by-the-named-project",
        path="intents/resolve.py",
        before=(
            "            if entry is not None and field in model.model_fields "
            "and field not in known:"
        ),
        after="            if False:",
        case=_WORDS + "test_refusals_and_object_lists_name_things_in_words",
        runner="pytest",
    ),
    Mutation(
        name="fix3-p1-files-in-the-named-dataset",
        path="intents/group_fill.py",
        before='    dataset = in_scope("dataset_id", value.get("dataset_id"), state, catalog)',
        after='    dataset = context_value("dataset_id", state, catalog)',
        case=_PARTS + "test_files_are_found_in_the_dataset_the_words_or_selection_name",
        runner="pytest",
    ),
    Mutation(
        name="fix3-p2-tasks-follow-their-package-and-file",
        path="storage/display_order.py",
        before="            positions.get(task.sample_id, len(positions)),\n",
        after="",
        case=_SCOPE + "test_lists_reads_and_the_planner_count_in_one_display_order",
        runner="pytest",
    ),
    Mutation(
        name="fix3-p2-packages-in-creation-order",
        path="storage/display_order.py",
        before="    return sorted(packages, key=package_key)",
        after="    return sorted(packages, key=lambda package: package.id)",
        case=_SCOPE + "test_lists_reads_and_the_planner_count_in_one_display_order",
        runner="pytest",
    ),
)

STATE_AND_WORDS_MUTATIONS = (
    Mutation(
        name="fix3-p3-derivable-values-are-never-asked",
        path="intents/validate.py",
        before="    asked = [name for name in missing if not derivable(step.action, name)]",
        after="    asked = list(missing)",
        case=_WORDS + "test_a_review_with_nothing_saved_says_why_instead_of_asking",
        runner="pytest",
    ),
    Mutation(
        name="fix3-p3-publishing-uses-the-newest-version",
        path="intents/derived.py",
        before='    "publish_label_set": {"version": _newest_version},',
        after='    "publish_label_set": {},',
        case=_WORDS + "test_newest_versions_are_read_not_asked",
        runner="pytest",
    ),
    Mutation(
        name="fix3-p4-outgoing-check-finds-choice-words",
        path="intents/public_text.py",
        before="        found += [word for word in WORD.findall(rest) if word in ZH_CHOICES]",
        after="        found += []",
        case=_WORDS + "test_the_outgoing_check_repairs_known_names_and_replaces_the_rest",
        runner="pytest",
    ),
    Mutation(
        name="fix3-p4-refusal-names-the-scope-in-words",
        path="intents/wording.py",
        before="    joined = scope_words(scopes, language)",
        after='    joined = ", ".join(scopes)',
        case=_WORDS + "test_refusals_and_object_lists_name_things_in_words",
        runner="pytest",
    ),
    Mutation(
        name="fix3-p4-object-lists-are-read-aloud",
        path="intents/answers.py",
        before='        "production_objects": objects_text,\n',
        after="",
        case=_WORDS + "test_refusals_and_object_lists_name_things_in_words",
        runner="pytest",
    ),
    Mutation(
        name="fix3-p4-card-revision-in-words",
        path="intents/describe.py",
        before="    if isinstance(value, str) and field in REVISIONS:",
        after="    if False:",
        case=_WORDS + "test_cards_show_revisions_tasks_and_budgets_in_words",
        runner="pytest",
    ),
    Mutation(
        name="fix3-p4-default-limits-in-words",
        path="intents/describe.py",
        before="        if isinstance(default, BaseModel):",
        after="        if False:",
        case=_WORDS + "test_cards_show_revisions_tasks_and_budgets_in_words",
        runner="pytest",
    ),
)

PARTS_MUTATIONS = (
    Mutation(
        name="fix3-p5-a-taken-new-name-is-asked",
        path="intents/resolve.py",
        before="            found = taken(self.db, step, self.catalog)",
        after="            found = None",
        case=_ACTIONS + "test_a_new_name_that_exists_is_said_and_never_planned_as_a_copy",
        runner="pytest",
    ),
    Mutation(
        name="fix3-p6-the-only-project-is-assumed",
        path="intents/resolve.py",
        before="            if len(own) != 1:",
        after="            if True:",
        case=_ACTIONS + "test_a_read_without_a_project_uses_the_speaker_s_only_one_and_says_so",
        runner="pytest",
    ),
    Mutation(
        name="fix3-p7-refused-part-is-set-aside",
        path="intents/partial.py",
        before="    if len(draft.steps) < 2:  # noqa: PLR2004",
        after="    if True:",
        case=_ACTIONS + "test_every_part_of_a_request_is_planned_or_said_why_not",
        runner="pytest",
    ),
    Mutation(
        name="fix3-p7-personal-project-keeps-no-assignments",
        path="intents/impossible.py",
        before='    return ("personal", 0) if _tier(db, step) == "personal" else None',
        after="    return None",
        case=_PARTS + "test_a_personal_project_says_it_keeps_no_assignments",
        runner="pytest",
    ),
    Mutation(
        name="fix3-p7-idle-part-is-set-aside",
        path="intents/resolve.py",
        before="            elif unchanged(self.db, step):",
        after="            elif False:",
        case=_PARTS + "test_a_part_that_changes_nothing_or_matches_nothing_is_set_aside",
        runner="pytest",
    ),
    Mutation(
        name="fix3-p7-empty-part-is-set-aside",
        path="intents/resolve.py",
        before=(
            "            return (without(draft, reasons) if len(draft.steps) > 1 else None) "
            "or empty"
        ),
        after="            return empty",
        case=_PARTS + "test_a_part_that_changes_nothing_or_matches_nothing_is_set_aside",
        runner="pytest",
    ),
    Mutation(
        name="fix3-p1-a-place-in-words-is-a-package-place",
        path="intents/group_fill.py",
        before="    number = place_number(position) if isinstance(position, (int, str)) else None",
        after="    number = task_number(position) if isinstance(position, (int, str)) else None",
        case=_PARTS + "test_places_names_and_choices_said_in_words_are_understood",
        runner="pytest",
    ),
    Mutation(
        name="fix3-p1-a-selection-dataset-by-name",
        path="intents/fill.py",
        before=(
            "    return _selection_dataset(value, current, state, catalog) "
            'if field == "selection" else value'
        ),
        after="    return value",
        case=_PARTS + "test_places_names_and_choices_said_in_words_are_understood",
        runner="pytest",
    ),
    Mutation(
        name="fix3-p4-choices-said-in-words",
        path="intents/signatures.py",
        before="    if len(said) == 1:\n        return said[0]\n",
        after="",
        case=_PARTS + "test_places_names_and_choices_said_in_words_are_understood",
        runner="pytest",
    ),
    Mutation(
        name="fix3-already-so-ignores-letter-case",
        path="intents/verify.py",
        before="        key: value.casefold() if isinstance(value, str) else value",
        after="        key: value",
        case=_PARTS + "test_places_names_and_choices_said_in_words_are_understood",
        runner="pytest",
    ),
    Mutation(
        name="fix3-already-so-ignores-a-repeated-chinese-name",
        path="intents/verify.py",
        before='    if label.get("name_zh") == label.get("name"):',
        after="    if False:",
        case=_PARTS + "test_places_names_and_choices_said_in_words_are_understood",
        runner="pytest",
    ),
    Mutation(
        name="fix3-p5-no-publish-slipped-into-a-plan",
        path="intents/verify.py",
        before="            or _publish_problem(step, state.text)\n",
        after="",
        case=_PARTS + "test_a_publish_nobody_asked_for_is_never_added",
        runner="pytest",
    ),
    Mutation(
        name="fix3-p7-an-edit-without-a-change-is-asked",
        path="intents/validate.py",
        before="    changes = nothing_to_edit(step)",
        after="    changes = ()",
        case=_PARTS + "test_an_edit_without_a_change_asks_what_to_change",
        runner="pytest",
    ),
    Mutation(
        name="fix3-p7-review-tasks-are-held-for-review",
        path="intents/group_fill.py",
        before='    stage = explicit if isinstance(explicit, str) and explicit else "annotation"',
        after='    stage = "annotation"',
        case=_PARTS + "test_review_tasks_and_remaining_files_are_the_ones_meant",
        runner="pytest",
    ),
    Mutation(
        name="fix3-p7-one-value-said-becomes-a-list",
        path="intents/signatures.py",
        before="        return [value]",
        after="        return value",
        case=_PARTS + "test_one_value_said_where_a_list_is_taken_becomes_a_list",
        runner="pytest",
    ),
    Mutation(
        name="fix3-draft-versions-can-be-compared",
        path="storage/production_objects.py",
        before=(
            "        after = require_label_set(session, identifier, query.after_version, "
            "published=False)"
        ),
        after="        after = require_label_set(session, identifier, query.after_version)",
        case=_PARTS + "test_a_draft_version_can_be_compared_and_unanswerable_asks_are_plain",
        runner="pytest",
    ),
    Mutation(
        name="fix3-skill-card-counts-its-holders",
        path="intents/describe.py",
        before="        + _holders(db, step, language)\n",
        after="",
        case=_ACTIONS + "test_a_skill_edit_card_says_how_many_people_hold_it",
        runner="pytest",
    ),
    Mutation(
        name="fix3-annotation-examples-are-existing-annotations",
        path="label_drafts/complete.py",
        before="    labelled = frozenset(sample.id for sample in inputs.samples if sample.labels)",
        after="    labelled: frozenset[str] = frozenset()",
        case=_ACTIONS
        + "test_an_annotation_only_draft_says_its_examples_came_from_existing_annotations",
        runner="pytest",
    ),
    Mutation(
        name="fix3-p7-read-survives-a-repair-that-gives-up",
        path="intents/planner.py",
        before='    if repaired.kind == "none" and draft.kind == "answer" and draft.steps:',
        after="    if False:",
        case=_ACTIONS + "test_a_read_the_repair_gives_up_on_is_still_answered_without_that_filter",
        runner="pytest",
    ),
)

INTENT_FIX3_MUTATIONS = (
    *NAMES_AND_ORDER_MUTATIONS,
    *STATE_AND_WORDS_MUTATIONS,
    *PARTS_MUTATIONS,
    *LIMITS_MUTATIONS,
    *OWNER_MUTATIONS,
)
