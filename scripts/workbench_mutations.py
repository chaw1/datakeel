# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Measured workbench source authorization, geometry and lossless interchange anchors."""

from scripts.mutation_models import Mutation

WORKBENCH_MUTATIONS = (
    Mutation(
        name="workbench-prelabel-duplicate-multiplicity",
        path="storage/workbench_risk.py",
        before="1 - sum((left & right).values()) / sum(union.values())",
        after="1 - len(left & right) / len(union)",
        case="tests/storage/test_workbench_risk.py::test_prelabel_difference_keeps_shape_attributes_and_excludes_provenance",
        runner="pytest",
    ),
    Mutation(
        name="workbench-prelabel-approved-human-reference",
        path="storage/production_statistics.py",
        before='if approved is None or approved.source != "human":',
        after="if approved is None:",
        case="tests/storage/test_workbench_accuracy.py::test_prelabel_accuracy_requires_approved_human_reference_and_model_history",
        runner="pytest",
    ),
    Mutation(
        name="workbench-prelabel-exact-approved-properties",
        path="storage/production_statistics.py",
        before="exact += prelabel_difference(approved.annotation, model.annotation) == 0",
        after="exact += True",
        case="tests/storage/test_workbench_accuracy.py::test_prelabel_accuracy_compares_latest_preceding_model_with_exact_approved_properties",
        runner="pytest",
    ),
    Mutation(
        name="workbench-enabled-template-components",
        path="storage/production_catalog.py",
        before="if isinstance(configured, list)",
        after="if False",
        case="tests/api/test_workbench.py::test_workbench_mixed_template_accepts_its_configured_components",
        runner="pytest",
    ),
    Mutation(
        name="workbench-package-before-pagination",
        path="storage/workbench_reads.py",
        before="ProductionTaskRow.package_id == query.package_id",
        after="ProductionTaskRow.project_id == project_id",
        case="tests/api/test_workbench.py::test_workbench_package_filter_precedes_pagination_and_keeps_project_progress",
        runner="pytest",
    ),
    Mutation(
        name="workbench-exif-coordinate-frame",
        path="api/routes/production.py",
        before="if image.getexif().get(274) not in (None, 1):",
        after="if False:",
        case="tests/api/test_workbench.py::test_workbench_exif_media_and_thumbnails_use_the_same_source_pixel_frame",
        runner="pytest",
    ),
    Mutation(
        name="workbench-model-confidence-after-human-save",
        path="storage/workbench_risk.py",
        before="model_confidence=model.confidence if model else None,",
        after="model_confidence=None,",
        case="tests/storage/test_workbench_risk.py::test_model_risk_survives_human_save_and_review_pagination",
        runner="pytest",
    ),
    Mutation(
        name="workbench-source-query-grant",
        path="storage/workbench_reads.py",
        before=(
            'require_access(db, (AssetRef(asset_type="production_task", asset_id=task_id),), '
            "caller)"
        ),
        after="pass",
        case="tests/api/test_workbench.py::test_workbench_protected_project_and_media_require_current_actor_grant",
        runner="pytest",
    ),
    Mutation(
        name="workbench-polygon-image-bounds",
        path="storage/production_catalog.py",
        before="point.x > annotation.image_width",
        after="False",
        case="tests/api/test_workbench.py::test_workbench_direct_polygon_save_rejects_outside_image_coordinates",
        runner="pytest",
    ),
    Mutation(
        name="workbench-native-record-attributes",
        path="training/native.py",
        before='rows.append(json_text(item.annotation.model_dump(mode="json")))',
        after=(
            'rows.append(json_text(item.annotation.model_copy(update={"attributes": {}})'
            '.model_dump(mode="json")))'
        ),
        case="tests/actions/test_workbench_roundtrip.py::test_all_components_roundtrip_finalization_export_and_reimport[polygon]",
        runner="pytest",
    ),
    Mutation(
        name="workbench-review-prelabel-difference",
        path="storage/workbench_risk.py",
        before="-differences[task.id],",
        after="0,",
        case="tests/storage/test_workbench_risk.py::test_review_order_prioritizes_round_then_confidence_then_difference",
        runner="pytest",
    ),
    Mutation(
        name="workbench-thumbnail-downsample",
        path="api/routes/production.py",
        before="preview.thumbnail((1024, 1024))",
        after="pass",
        case="tests/api/test_workbench.py::test_workbench_large_image_preview_is_downsampled_before_high_resolution_source",
        runner="pytest",
    ),
)
