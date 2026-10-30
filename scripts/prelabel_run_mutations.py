# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""P31a FIX1/FIX2 anchors for prelabel runs, pass-through and the review rules.

Runs outside transactions, accountable and signed pass-through, the calibration curve, human
heads left alone, and near-duplicates compared on the annotation kinds both sides recorded.
"""

from scripts.mutation_models import Mutation

_RUNNER = "tests/storage/test_production_cloud_runner.py::"
_ROUTING = "tests/storage/test_production_confidence_routing.py::"
_TIERS = "tests/annotation_qa/test_confidence_tiers.py::"
_POLICY = "tests/storage/test_production_pass_through_policy.py::"
_TARGETS = "tests/storage/test_production_prelabel_targets.py::"
_RULES = "tests/annotation_qa/test_review_rules.py::"

PRELABEL_RUN_MUTATIONS = (
    Mutation(
        name="prelabel-run-one-live-run-per-project",
        path="storage/production_prelabel_runs.py",
        before="if now - (run.updated_at or run.created_at) < STALE_AFTER:",
        after="if False:",
        case=_RUNNER
        + "test_a_second_live_run_on_the_project_is_refused_until_the_first_goes_silent",
        runner="pytest",
    ),
    Mutation(
        name="prelabel-run-takeover-stops-sending",
        path="storage/production_cloud_runner.py",
        before="ledger.taken_over = True",
        after="pass",
        case=_RUNNER + "test_a_run_taken_over_writes_nothing_more_and_fails_its_action",
        runner="pytest",
    ),
    Mutation(
        name="prelabel-run-keeps-newer-human-head",
        path="storage/production_cloud_runner.py",
        before="if target.id in tasks and tasks[target.id].latest_revision_id != target.head",
        after="if False",
        case=_RUNNER + "test_a_draft_never_lands_on_work_a_person_saved_while_the_model_ran",
        runner="pytest",
    ),
    Mutation(
        name="prelabel-run-failure-names-the-file",
        path="storage/production_cloud_runner.py",
        before="filename=run.filenames.get(task.sample_id, task.sample_id),",
        after="filename=task.sample_id,",
        case=_RUNNER + "test_failures_name_the_file_and_keep_the_sample_apart",
        runner="pytest",
    ),
    Mutation(
        name="tier-pav-pools-violators",
        path="annotation_qa/confidence_tiers.py",
        before="while len(blocks) > 1 and blocks[-2][3] * blocks[-1][2]"
        " > blocks[-1][3] * blocks[-2][2]:",
        after="while False:",
        case=_TIERS + "test_violating_neighbours_are_pooled_into_one_flat_segment",
        runner="pytest",
    ),
    Mutation(
        name="tier-default-thresholds-never-pass-through",
        path="annotation_qa/confidence_tiers.py",
        before='"pass_through": measured or configured[0] is not None,',
        after='"pass_through": True,',
        case=_TIERS + "test_insufficient_samples_fall_back_to_defaults_with_reason",
        runner="pytest",
    ),
    Mutation(
        name="tier-cold-start-holds-high-drafts",
        path="storage/production_tiers.py",
        before='elif tier == "high" and pass_through:',
        after='elif tier == "high":',
        case=_ROUTING + "test_cold_start_defaults_hold_high_drafts_for_a_person",
        runner="pytest",
    ),
    Mutation(
        name="pass-through-trigger-is-the-annotator",
        path="storage/production_prelabel_writes.py",
        before="task.annotator_id = actor",
        after="pass",
        case=_ROUTING + "test_team_pass_through_keeps_its_trigger_out_of_review",
        runner="pytest",
    ),
    Mutation(
        name="pass-through-is-audited",
        path="storage/production_ai_audit.py",
        before='if tier.routed != "submitted" or revision is None'
        " or revision.pass_through is None:",
        after="if True:",
        case=_ROUTING + "test_pass_through_names_the_model_the_bar_and_the_person_who_ran_it",
        runner="pytest",
    ),
    Mutation(
        name="review-names-the-annotator-not-the-reviewer",
        path="storage/production_reviews.py",
        before="annotator_id=_annotator(session, task),",
        after="annotator_id=task.annotator_id or actor,",
        case=_ROUTING + "test_review_of_a_pass_through_names_the_trigger_not_the_reviewer",
        runner="pytest",
    ),
    Mutation(
        name="submit-refuses-a-model-head",
        path="storage/production_reviews.py",
        before='if head is not None and head.source == "model":',
        after="if False:",
        case=_ROUTING
        + "test_a_model_head_is_submitted_only_after_the_annotator_saves_it_as_their_own",
        runner="pytest",
    ),
    Mutation(
        name="pass-through-relaxing-needs-approval",
        path="storage/production_review_policy.py",
        before="widened = new is not None and (old is None or new < old)",
        after="widened = False",
        case=_POLICY + "test_a_manual_bar_over_cold_start_and_any_lower_bar_need_approval",
        runner="pytest",
    ),
    Mutation(
        name="cloud-prelabel-skips-human-heads",
        path="storage/production_cloud_prelabel.py",
        before="eligible = [task for task in editable if task.id not in human]",
        after="eligible = editable",
        case=_TARGETS + "test_cloud_run_skips_and_counts_tasks_a_person_already_saved",
        runner="pytest",
    ),
    Mutation(
        name="fake-prelabel-skips-human-heads",
        path="storage/production_predictions.py",
        before="if task.id in human:",
        after="if False:",
        case=_TARGETS + "test_fake_run_leaves_a_person_saved_task_alone",
        runner="pytest",
    ),
    Mutation(
        name="review-compares-only-shared-kinds",
        path="annotation_qa/review_rules.py",
        before="if getattr(left, field) is None or getattr(right, field) is None",
        after="if False",
        case=_RULES + "test_a_box_only_draft_says_nothing_about_the_chosen_classification",
        runner="pytest",
    ),
)
