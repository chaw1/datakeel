# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""FIX6 anchors: every state-changing action's needs, later turns, groups and the exit."""

from scripts.mutation_models import Mutation

_T = "tests/intents/test_fix6_"


def _anchor(name: str, path: str, change: tuple[str, str], case: str) -> Mutation:
    before, after = change
    return Mutation(
        name=f"fix6-{name}", path=path, before=before, after=after, case=_T + case, runner="pytest"
    )


FIX6_MUTATIONS = (
    _anchor(
        "a-later-turns-back-reference-is-the-earlier-object",
        "intents/fill.py",
        (
            (
                "    back = earlier_object(field, current.params[field], state)  "
                '# "刚才那个": last turn\'s'
            ),
            "    back = None",
        ),
        "turns.py::test_those_tasks_in_a_later_turn_are_the_ones_just_assigned",
    ),
    _anchor(
        "the-previous-turn-keeps-objects-of-every-kind",
        "intents/planner.py",
        (
            '            for key in {*CONTAINER_OUTPUTS, *FIELD_KINDS, "task_ids"}:',
            "            for key in CONTAINER_OUTPUTS:",
        ),
        "turns.py::test_that_person_in_a_later_turn_is_the_one_named_before",
    ),
    _anchor(
        "a-model-registered-earlier-is-not-looked-up",
        "intents/created.py",
        (
            '        _known(created, "model", model.get("id"), (model.get("name"),))',
            "        pass",
        ),
        "create.py::test_a_model_registered_earlier_in_the_plan_is_used_by_name_or_as_it",
    ),
    _anchor(
        "it-in-a-plan-is-the-one-object-made-earlier",
        "intents/created.py",
        ("    if BACK.match(item.strip()) and len(made) == 1:", "    if False:"),
        "create.py::test_a_model_registered_earlier_in_the_plan_is_used_by_name_or_as_it",
    ),
    _anchor(
        "the-next-n-come-after-the-ones-taken",
        "intents/segments.py",
        ("    if not _segmented(spec, state, action):", "    if True:"),
        "groups.py::test_the_next_two_are_counted_after_the_first_two",
    ),
    _anchor(
        "one-group-for-two-steps-is-one-set",
        "intents/segments.py",
        (
            (
                "    same = [] if _segmented(spec, state, action) else "
                "state.chosen.get(_key(spec), [])"
            ),
            "    same = []",
        ),
        "groups.py::test_revoke_then_reassign_acts_on_one_set_and_protection_spares_both",
    ),
    _anchor(
        "one-action-never-takes-the-same-place-twice",
        "intents/segments.py",
        (
            "    return NEXT.search(state.text) is not None or action in state.taken",
            "    return NEXT.search(state.text) is not None",
        ),
        "groups.py::test_one_action_given_the_same_first_one_twice_takes_the_next",
    ),
    _anchor(
        "a-later-step-keeps-what-only-it-can-take",
        "intents/segments.py",
        (
            "    merged = [*same, *(task for task in ids if task not in same)]",
            "    merged = same or ids",
        ),
        "groups.py::test_a_later_step_of_the_same_group_keeps_what_only_it_can_take",
    ),
    _anchor(
        "a-question-beside-a-change-keeps-the-change",
        "intents/readonly.py",
        (
            (
                '    if draft.kind != "plan" or len(writes) < len(draft.steps) or not '
                "status_question(text):"
            ),
            '    if draft.kind != "plan" or not writes or not status_question(text):',
        ),
        "reads.py::test_a_change_asked_beside_a_question_still_plans",
    ),
    _anchor(
        "the-persons-words-win-over-the-models-id",
        "intents/fill.py",
        ("    if len(spoken) == 1 and spoken[0] not in found:", "    if False:"),
        "create.py::test_the_persons_words_win_over_the_models_identity",
    ),
    _anchor(
        "template-roles-have-their-chinese-names",
        "intents/catalog.py",
        (
            "            names=(role.id, role.name, *ROLE_WORDS.get(role.id, ())),",
            "            names=(role.id, role.name),",
        ),
        "create.py::test_template_roles_are_found_by_their_chinese_names",
    ),
    _anchor(
        "a-reference-in-a-list-is-a-reference",
        "intents/model_parse.py",
        (
            (
                "        params[key] = [_ref(item) for item in value] if isinstance(value, list) "
                "else _ref(value)"
            ),
            "        params[key] = _ref(value)",
        ),
        "create.py::test_a_reference_inside_a_list_is_the_object_made_earlier",
    ),
    _anchor(
        "a-listed-reference-is-the-object-made-earlier",
        "intents/created.py",
        ('    if isinstance(item, dict) and "$ref" in item and len(made) == 1:', "    if False:"),
        "create.py::test_a_reference_inside_a_list_is_the_object_made_earlier",
    ),
    _anchor(
        "each-groups-first-file-follows-the-list",
        "intents/selectors.py",
        (
            "            left, right = sorted(pair, key=shown.__getitem__)",
            "            left, right = sorted(pair)",
        ),
        "groups.py::test_each_groups_first_file_is_the_one_the_list_shows_first",
    ),
    _anchor(
        "handing-in-needs-the-task-held-and-saved",
        "intents/preconditions.py",
        (
            '    "submit_task": ("finalized", "held", "saved_and_open"),',
            '    "submit_task": ("finalized",),',
        ),
        "checks.py::test_an_unmet_precondition_says_what_is_missing_and_what_first[submit-unsaved]",
    ),
    _anchor(
        "every-action-on-work-declares-its-needs",
        "intents/preconditions.py",
        ('    "split_packages": ("finalized", "not_split"),', ""),
        "checks.py::test_every_registered_action_on_work_declares_its_preconditions",
    ),
    _anchor(
        "what-the-state-lacks-is-said-before-a-value-is-asked",
        "intents/validate.py",
        (
            "    reason = unmet(db, acting, actor, language, previous) if missing else None",
            "    reason = None",
        ),
        "checks.py::test_an_unmet_precondition_says_what_is_missing_and_what_first[accept-not-team]",
    ),
    _anchor(
        "an-earlier-step-can-meet-a-need",
        "intents/preconditions.py",
        ("        if rule.changed_by & changed:", "        if False:"),
        "checks.py::test_an_earlier_step_that_meets_the_need_lets_the_plan_through",
    ),
    _anchor(
        "already-so-states-the-current-state",
        "intents/already.py",
        (
            "    return reason if reason not in IDLE else stated(db, step, catalog, language)",
            "    return reason",
        ),
        "checks.py::test_a_change_to_what_is_already_so_states_the_current_state",
    ),
    _anchor(
        "a-models-name-gives-its-version",
        "intents/named_kinds.py",
        ('    if spoken and not record.get("version"):', "    if False:"),
        "create.py::test_what_a_new_models_name_says_is_never_asked",
    ),
    _anchor(
        "a-skills-name-gives-its-type",
        "intents/object_edits.py",
        ('        named_skill_type(params)  # "夜间行人框选" is a box skill', "        pass"),
        "create.py::test_a_new_skills_type_comes_from_its_name",
    ),
    _anchor(
        "an-emptied-name-is-put-into-words",
        "intents/public_text.py",
        (
            'EMPTY_NAME = (re.compile(r"叫「\\s*」的|「\\s*」"), re.compile(r\'called ""|""\'))',
            'EMPTY_NAME = (re.compile(r"叫「\\s*」的"), re.compile(r\'called ""\'))',
        ),
        "checks.py::test_internal_names_never_leave_and_never_become_the_blank_sentence"
        "[empty-quote]",
    ),
    _anchor(
        "a-name-among-the-choices-is-asked-as-several",
        "intents/public_text.py",
        (
            '        update["text"] = _ambiguous(str(update["text"]), offered, language)',
            '        update["text"] = str(update["text"])',
        ),
        "checks.py::test_a_not_found_name_among_the_choices_is_asked_as_ambiguous",
    ),
    _anchor(
        "a-clear-rule-reading-is-checked-as-that-action",
        "intents/landing.py",
        ("CLEAR_SCORE = 0.9", "CLEAR_SCORE = 9.0"),
        "scope.py::test_a_none_that_names_the_one_action_that_does_it_is_checked_as_it",
    ),
    _anchor(
        "a-none-weighing-several-actions-is-not-forced",
        "intents/landing.py",
        ("    named = draft.related == [top]", "    named = top in draft.related"),
        "scope.py::test_a_none_weighing_several_actions_stays_missing",
    ),
    _anchor(
        "own-work-in-one-project-is-answered",
        "intents/read_scope.py",
        (
            "    own = len(mine) > 1 and len(working) == 1 and SELF.search(text) is not None",
            "    own = False",
        ),
        "scope.py::test_own_work_in_one_project_is_answered_for_it_and_says_so",
    ),
    _anchor(
        "a-named-setting-is-asked-its-value",
        "intents/what_changes.py",
        ("    named = _named(step, changes, said[0])", "    named = None"),
        "scope.py::test_a_named_setting_is_asked_for_its_value_with_the_allowed_ones",
    ),
    _anchor(
        "a-missing-file-selection-offers-choices",
        "intents/validate.py",
        (
            (
                '    if field == "selection":  # "把那张图隔离": the dataset\'s files, '
                "or the datasets, to pick"
            ),
            "    if False:",
        ),
        "scope.py::test_a_missing_file_selection_offers_files_or_datasets",
    ),
    _anchor(
        "near-duplicates-not-computed-are-said-computing",
        "intents/selectors.py",
        (
            '        return {**empty, "$empty": True, **({"$pending": True} if waiting else {})}',
            '        return {**empty, "$empty": True}',
        ),
        "scope.py::test_near_duplicates_not_yet_computed_are_said_to_be_computing",
    ),
    _anchor(
        "a-status-question-is-read-not-changed",
        "intents/planner.py",
        (
            (
                "    draft = read_only(fitted(draft, ranked), turn.text, ranked)  "
                '# "定稿了吗?" is a read'
            ),
            "    draft = fitted(draft, ranked)",
        ),
        "reads.py::test_a_write_proposed_for_status_finalize_becomes_a_read",
    ),
    _anchor(
        "a-request-is-never-a-status-question",
        "intents/readonly.py",
        ("    if REQUEST.search(text):", "    if False:"),
        "reads.py::test_requests_are_never_taken_for_questions[is-it-possible]",
    ),
    _anchor(
        "submitted-work-is-not-taken-back",
        "intents/preconditions.py",
        (
            '"revoke_assignment": ("finalized", "revocable"),',
            '"revoke_assignment": ("finalized",),',
        ),
        "checks.py::test_an_unmet_precondition_says_what_is_missing_and_what_first[revoke-submitted]",
    ),
    _anchor(
        "a-group-project-has-no-lease-to-renew",
        "intents/preconditions.py",
        ('"heartbeat": ("finalized", "leased"),', '"heartbeat": ("finalized",),'),
        "checks.py::test_an_unmet_precondition_says_what_is_missing_and_what_first[heartbeat-group]",
    ),
    _anchor(
        "nothing-free-is-not-claimed",
        "intents/preconditions.py",
        ('"claim_task": ("finalized", "free_task"),', '"claim_task": ("finalized",),'),
        "checks.py::test_an_unmet_precondition_says_what_is_missing_and_what_first"
        "[claim-nothing-free]",
    ),
    _anchor(
        "a-free-task-can-be-claimed",
        "intents/preconditions.py",
        ("    if any(task.id not in holders for task in tasks):", "    if not tasks:"),
        "checks.py::test_a_package_with_a_free_task_can_be_claimed_from",
    ),
    _anchor(
        "joined-ids-are-several",
        "intents/model_parse.py",
        ("        value = _ids(key, given)", "        value = given"),
        "turns.py::test_ids_copied_as_one_joined_string_are_still_several[joined]",
    ),
    _anchor(
        "a-requirement-type-said-in-words-is-registered",
        "intents/fill.py",
        (
            '    spoken_requirement(params)  # "分类标注" in a skill requirement is classification',
            "    pass",
        ),
        "create.py::test_a_skill_requirement_said_in_words_is_the_registered_type",
    ),
    _anchor(
        "the-minimum-level-has-a-label",
        "intents/field_names.py",
        ('    "min_level": ("最低等级", "minimum level"),\n', ""),
        "create.py::test_a_skill_requirement_said_in_words_is_the_registered_type",
    ),
    _anchor(
        "this-without-a-page-object-is-the-previous-turns",
        "intents/fill_state.py",
        (
            "    this = THIS.match(value.strip()) and getattr(state.context, field, None) is None",
            "    this = False",
        ),
        "turns.py::test_this_project_in_a_later_turn_is_the_one_just_changed",
    ),
    _anchor(
        "nothing-matched-is-not-several",
        "intents/fill_state.py",
        ("    several = matched and len(choices) > 1", "    several = len(choices) > 1"),
        "turns.py::test_a_name_that_matches_nothing_is_not_said_to_match_several",
    ),
    _anchor(
        "a-version-is-found-by-its-shown-label",
        "intents/catalog.py",
        (
            (
                '                f"{name} · v{number}",  '
                "# the label the planner is shown, copied back\n"
            ),
            "",
        ),
        "create.py::test_a_version_named_by_its_shown_label_is_found",
    ),
    _anchor(
        "a-task-taken-back-is-back-in-the-queue",
        "intents/segments.py",
        (
            'update={"holder": None, "stage": None, "state": RETURN_STATE[task.stage]}',
            'update={"holder": None, "stage": None}',
        ),
        "groups.py::test_a_task_taken_back_earlier_is_back_in_the_queue_for_unheld_work",
    ),
    _anchor(
        "an-action-name-as-a-scope-grants-it",
        "intents/object_edits.py",
        (
            "| {POLICIES[name][0] for name in named if name in POLICIES}",
            "| set()",
        ),
        "create.py::test_action_names_written_as_scopes_grant_those_actions",
    ),
)
