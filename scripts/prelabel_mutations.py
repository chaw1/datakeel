# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""P31a anchors: IoU matching, cloud budget and reruns, confidence tiers and AI pre-review."""

from scripts.mutation_models import Mutation

_CLOUD = "tests/storage/test_production_cloud_prelabel.py::"
_ROUTING = "tests/storage/test_production_confidence_routing.py::"
_REVIEW = "tests/storage/test_production_ai_review.py::"
_RULES = "tests/storage/test_production_ai_rules.py::"
_TIERS = "tests/annotation_qa/test_confidence_tiers.py::"
_ADAPTER = "tests/prelabel/test_prelabel_adapter.py::"

PRELABEL_MUTATIONS = (
    Mutation(
        name="prelabel-match-greedy-by-iou",
        path="annotation_qa/prelabel_match.py",
        before="key=lambda item: (-item[0], item[1], item[2]),",
        after="key=lambda item: (item[1], -item[0], item[2]),",
        case="tests/annotation_qa/test_prelabel_match.py::"
        "test_greedy_takes_highest_iou_pair_first_not_detection_order",
        runner="pytest",
    ),
    Mutation(
        name="prelabel-strict-iou-tier",
        path="annotation_qa/prelabel_match.py",
        before="STRICT_IOU = 0.75",
        after="STRICT_IOU = 0.5",
        case="tests/storage/test_production_prelabel_iou.py::"
        "test_iou_accuracy_counts_geometric_hits_and_reports_attributes_apart",
        runner="pytest",
    ),
    Mutation(
        name="prelabel-cloud-budget-stop",
        path="storage/production_cloud_runner.py",
        before="if planned + next_cost > budget:",
        after="if False:",
        case=_CLOUD + "test_budget_stops_mid_run_and_rerun_only_fills_unrun_images",
        runner="pytest",
    ),
    Mutation(
        name="prelabel-cloud-rerun-skips-done",
        path="storage/production_cloud_prelabel.py",
        before="task.state in EDITABLE_STATES and task.id not in done",
        after="task.state in EDITABLE_STATES",
        case=_CLOUD + "test_failure_list_names_each_class_and_rerun_retries_only_failures",
        runner="pytest",
    ),
    Mutation(
        name="prelabel-cloud-estimate-approval",
        path="storage/production_catalog_plans.py",
        before="return Decimal(str(estimate.total)) > Decimal(str(params.budget))",
        after="return False",
        case=_CLOUD + "test_budget_stops_mid_run_and_rerun_only_fills_unrun_images",
        runner="pytest",
    ),
    Mutation(
        name="prelabel-rate-limit-code",
        path="prelabel/client.py",
        before='return _failure("rate_limited", started)',
        after='return _failure("provider_error_429", started)',
        case=_CLOUD + "test_failure_list_names_each_class_and_rerun_retries_only_failures",
        runner="pytest",
    ),
    Mutation(
        name="prelabel-out-of-bounds-drop",
        path="prelabel/parse.py",
        before="if x1 < 0 or y1 < 0 or x2 > view.width or y2 > view.height:",
        after="if False:",
        case=_ADAPTER + "test_parse_maps_normalized_boxes_to_source_pixels_and_drops_bad_ones",
        runner="pytest",
    ),
    Mutation(
        name="prelabel-mirrored-view-unmirrored",
        path="prelabel/parse.py",
        before="x1, x2 = view.width - x2, view.width - x1",
        after="x1, x2 = x1, x2",
        case=_ADAPTER + "test_parse_unmirrors_and_reads_pixel_space_and_labels",
        runner="pytest",
    ),
    Mutation(
        name="prelabel-missing-usage-still-priced",
        path="storage/production_cloud_labeling.py",
        before="if reply.failure is None and not reply.usage_reported:",
        after="if False:",
        case=_CLOUD + "test_missing_usage_is_priced_from_the_estimate",
        runner="pytest",
    ),
    Mutation(
        name="tier-high-threshold-inclusive-rate",
        path="annotation_qa/confidence_tiers.py",
        before="if segment.rate >= HIGH_HIT_RATE:",
        after="if segment.rate > HIGH_HIT_RATE:",
        case=_TIERS + "test_known_hit_rates_give_the_documented_thresholds",
        runner="pytest",
    ),
    Mutation(
        name="tier-low-threshold-strict-rate",
        path="annotation_qa/confidence_tiers.py",
        before="if segment.rate >= LOW_HIT_RATE:",
        after="if segment.rate > LOW_HIT_RATE:",
        case=_TIERS + "test_known_hit_rates_give_the_documented_thresholds",
        runner="pytest",
    ),
    Mutation(
        name="tier-insufficient-samples-default",
        path="annotation_qa/confidence_tiers.py",
        before="measured = len(observations) >= MINIMUM_OBJECTS",
        after="measured = bool(observations)",
        case=_TIERS + "test_insufficient_samples_fall_back_to_defaults_with_reason",
        runner="pytest",
    ),
    Mutation(
        name="tier-task-takes-lowest-object",
        path="annotation_qa/confidence_tiers.py",
        before="return min((object_tier(value, high, low) for value in confidences)",
        after="return max((object_tier(value, high, low) for value in confidences)",
        case=_TIERS + "test_task_tier_is_the_lowest_object_and_empty_is_low",
        runner="pytest",
    ),
    Mutation(
        name="tier-high-routes-to-review",
        path="storage/production_tiers.py",
        before='routed = "submitted"',
        after='routed = "draft"',
        case=_ROUTING + "test_group_tiers_route_high_to_review_medium_to_draft_low_to_scratch",
        runner="pytest",
    ),
    Mutation(
        name="tier-personal-only-hints",
        path="storage/production_tiers.py",
        before='if project.workflow_tier == "personal" or task.state != "pending":',
        after='if task.state != "pending":',
        case=_ROUTING + "test_personal_tiers_are_only_hints",
        runner="pytest",
    ),
    Mutation(
        name="ai-review-high-risk-always-reviewed",
        path="storage/production_ai_review.py",
        before="elif high or draw < rate:",
        after="elif draw < rate:",
        case=_REVIEW + "test_low_risk_is_exempted_with_audit_and_high_risk_still_reviewed",
        runner="pytest",
    ),
    Mutation(
        name="ai-review-exemption-audited",
        path="storage/production_ai_audit.py",
        before='if review.decision == "exempt":',
        after="if False:",
        case=_REVIEW + "test_low_risk_is_exempted_with_audit_and_high_risk_still_reviewed",
        runner="pytest",
    ),
    Mutation(
        name="ai-review-lowering-needs-approval",
        path="storage/production_review_policy.py",
        before="return params.review_sample_rate < current",
        after="return False",
        case=_REVIEW + "test_lowering_the_ratio_needs_signed_approval",
        runner="pytest",
    ),
    Mutation(
        name="ai-review-personal-decision",
        path="storage/production_ai_review.py",
        before='decision, note = "personal", ""',
        after='decision, note = "review", ""',
        case=_REVIEW + "test_personal_submission_is_flagged_but_never_blocked",
        runner="pytest",
    ),
    Mutation(
        name="ai-review-queue-orders-by-risk",
        path="storage/workbench_risk.py",
        before="-scores[task.id],",
        after="0,",
        case="tests/storage/test_workbench_risk.py::"
        "test_model_risk_survives_human_save_and_review_pagination",
        runner="pytest",
    ),
    Mutation(
        name="ai-review-label-swap",
        path="annotation_qa/review_rules.py",
        before="if best[0] >= HIT_IOU:",
        after="if best[0] > 1:",
        case="tests/annotation_qa/test_review_rules.py::"
        "test_relabelling_a_confident_draft_box_is_a_high_risk_swap",
        runner="pytest",
    ),
    Mutation(
        name="ai-review-size-outlier-sees-drafts",
        path="storage/production_ai_rules.py",
        before="item.head.annotation if item.head else item.draft.record if item.draft else None",
        after="item.head.annotation if item.head else None",
        case=_RULES + "test_size_outlier_submitted_first_is_judged_against_draft_boxes",
        runner="pytest",
    ),
    Mutation(
        name="ai-review-near-duplicate-rescores-partner",
        path="storage/production_ai_review.py",
        before="if item.head is not None and item.state in _WAITING:",
        after="if False:",
        case=_RULES + "test_near_duplicate_conflict_flags_both_images_whatever_the_order[True]",
        runner="pytest",
    ),
    Mutation(
        name="ai-review-template-exclusive-groups",
        path="storage/production_ai_rules.py",
        before='raw = config.get("exclusive_label_groups")',
        after="raw = None",
        case=_RULES + "test_template_exclusive_labels_make_a_multiselect_conflict",
        runner="pytest",
    ),
    Mutation(
        name="ai-review-noisy-or",
        path="annotation_qa/risk_scoring.py",
        before="remaining *= 1 - weight",
        after="remaining = min(remaining, 1 - weight)",
        case=_TIERS + "test_noisy_or_risk_is_monotone_and_strong_rules_are_high_alone",
        runner="pytest",
    ),
)
