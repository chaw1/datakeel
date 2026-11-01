# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Targeted native-keypoint behavior anchors; full-catalog shards include these in CI."""

from scripts.mutation_models import Mutation

_CORE = "tests/core/test_keypoints.py::"
_STORAGE = "tests/storage/test_production_keypoints.py::"
_EXPORT = "tests/training/test_keypoint_export.py::"
_METRICS = "tests/annotation_qa/test_keypoint_metrics.py::"

KEYPOINT_MUTATIONS = (
    Mutation(
        name="keypoint-missing-can-carry-coordinates",
        path="core/annotation_models.py",
        before='if self.state == "missing" and (self.x is not None or self.y is not None):',
        after="if False:",
        case=_CORE + "test_point_states_require_the_documented_coordinate_shape",
        runner="pytest",
    ),
    Mutation(
        name="keypoint-save-loses-template-alignment",
        path="storage/production_catalog.py",
        before=(
            "return normalize_keypoints(template, normalized) "
            "if template is not None else normalized"
        ),
        after="return normalized",
        case=_STORAGE + "test_save_aligns_ids_and_draft_all_missing_cannot_submit",
        runner="pytest",
    ),
    Mutation(
        name="keypoint-submit-completeness-disabled",
        path="core/production_keypoints.py",
        before=(
            "        if complete:\n"
            "            _require_complete_skeleton(skeleton, definitions, index)"
        ),
        after=(
            "        if False:\n"
            "            _require_complete_skeleton(skeleton, definitions, index)"
        ),
        case=_CORE + "test_draft_allows_partial_but_submit_rejects_required_and_all_missing",
        runner="pytest",
    ),
    Mutation(
        name="keypoint-used-point-deletion-allowed",
        path="storage/production_keypoint_upgrades.py",
        before="    if not removed or before.id != after.id:\n        return",
        after="    if True:\n        return",
        case=_STORAGE + "test_used_point_cannot_be_deleted_or_renamed",
        runner="pytest",
    ),
    Mutation(
        name="keypoint-exif-conversion-dropped",
        path="core/image_orientation.py",
        before='    return skeleton.model_copy(update={"points": tuple(points)})',
        after="    return skeleton",
        case=_CORE + "test_exif_moves_positioned_points_and_preserves_missing[6]",
        runner="pytest",
    ),
    Mutation(
        name="keypoint-coco-occluded-becomes-visible",
        path="training/export_keypoints.py",
        before='values.extend((point.x, point.y, 2.0 if point.state == "visible" else 1.0))',
        after="values.extend((point.x, point.y, 2.0))",
        case=_EXPORT + "test_coco_matches_an_independent_keypoint_oracle",
        runner="pytest",
    ),
    Mutation(
        name="keypoint-coco-counts-missing-as-positioned",
        path="training/export_keypoints.py",
        before="num_keypoints=len(positioned),",
        after="num_keypoints=len(schema.points),",
        case=_EXPORT + "test_coco_matches_an_independent_keypoint_oracle",
        runner="pytest",
    ),
    Mutation(
        name="keypoint-unsupported-format-drops-skeletons",
        path="training/export_keypoints.py",
        before="    if has_keypoints(export):\n        message =",
        after="    if False:\n        message =",
        case=_EXPORT + "test_unsupported_formats_reject_instead_of_dropping_keypoints[yolo]",
        runner="pytest",
    ),
    Mutation(
        name="keypoint-coco-bounds-disabled",
        path="training/export_common.py",
        before="            if not 0 <= point.x <= width or not 0 <= point.y <= height:",
        after="            if False:",
        case=_EXPORT + "test_coco_rejects_out_of_bounds_native_keypoints",
        runner="pytest",
    ),
    Mutation(
        name="keypoint-coco-import-becomes-detection",
        path="training/importers.py",
        before=(
            "    if any(\n"
            "        category.keypoints is not None or category.skeleton is not None\n"
            "        for category in document.categories\n"
            "    ) or any(\n"
            "        annotation.keypoints is not None or annotation.num_keypoints is not None\n"
            "        for annotation in document.annotations\n"
            "    ):"
        ),
        after="    if False:",
        case=_EXPORT + "test_coco_keypoint_import_is_explicitly_rejected_even_with_bbox",
        runner="pytest",
    ),
    Mutation(
        name="keypoint-only-metrics-perfect-score",
        path="annotation_qa/prelabel_match.py",
        before=(
            "    return any(\n"
            "        getattr(model, field) is not None and getattr(human, field) is not None"
        ),
        after=(
            "    return True or any(\n"
            "        getattr(model, field) is not None and getattr(human, field) is not None"
        ),
        case=_METRICS + "test_keypoint_only_comparison_does_not_participate_in_iou_accuracy",
        runner="pytest",
    ),
    Mutation(
        name="keypoint-review-approve-skips-revalidation",
        path="storage/production_catalog.py",
        before="        validate_template_content(template, annotation, complete=True)",
        after="        validate_template_content(template, annotation, complete=False)",
        case=_STORAGE + "test_group_review_revalidates_approve_but_allows_rework",
        runner="pytest",
    ),
    Mutation(
        name="keypoint-team-acceptance-skips-revalidation",
        path="storage/production_acceptance.py",
        before="        require_complete_attributes(session, project, head.annotation)",
        after="        head.annotation",
        case=_STORAGE + "test_team_package_acceptance_revalidates_every_approved_skeleton",
        runner="pytest",
    ),
    Mutation(
        name="keypoint-finalize-skips-revalidation",
        path="storage/production_finalize.py",
        before="        require_complete_attributes(session, project, revision.annotation)",
        after="        revision.annotation",
        case=_STORAGE + "test_valid_skeleton_submits_and_finalization_rechecks_new_required_points",
        runner="pytest",
    ),
    Mutation(
        name="keypoint-placeholder-template-write-allowed",
        path="storage/production_keypoint_upgrades.py",
        before=(
            '    if "keypoints" in enabled_components(template):\n        require_schema(template)'
        ),
        after="    if False:\n        require_schema(template)",
        case=_STORAGE + "test_new_keypoint_template_and_project_require_schema",
        runner="pytest",
    ),
)
