# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Measured production vocabulary impact and prediction geometry regression anchors."""

from scripts.mutation_models import Mutation

PRODUCTION_CATALOG_MUTATIONS = (
    Mutation(
        name="production-stable-label-identity",
        path="storage/production_revisions.py",
        before="normalize_annotation(session, project, params.annotation)",
        after="params.annotation",
        case=(
            "tests/storage/test_production_template_validation.py::"
            "test_saved_display_names_and_ids_share_one_stable_annotation_identity"
        ),
        runner="pytest",
    ),
    Mutation(
        name="production-migration-exact-instance-count",
        path="storage/production_catalog_impact.py",
        before="annotations += count",
        after="annotations += bool(count)",
        case=(
            "tests/storage/test_production_catalog.py::"
            "test_migration_counts_latest_annotation_instances_exactly"
        ),
        runner="pytest",
    ),
    Mutation(
        name="production-prediction-image-bounds",
        path="storage/production_prediction_parsing.py",
        before="x + box_width > width + BOX_BOUNDS_TOLERANCE",
        after="False",
        case=(
            "tests/storage/test_production_prediction_parsing.py::"
            "test_coco_import_reports_each_bad_image_without_losing_valid_images"
        ),
        runner="pytest",
    ),
    Mutation(
        name="production-prediction-edge-roundoff",
        path="storage/production_prediction_parsing.py",
        before="BOX_BOUNDS_TOLERANCE = 1e-7",
        after="BOX_BOUNDS_TOLERANCE = 0.0",
        case=(
            "tests/storage/test_production_prediction_parsing.py::"
            "test_yolo_edge_roundoff_is_clipped_to_image_bounds[right]"
        ),
        runner="pytest",
    ),
)
