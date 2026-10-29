# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Training goldens and independent format assertions must kill these boundary changes."""

from scripts.mutation_models import Mutation

TRAINING_MUTATIONS = (
    Mutation(
        name="training-coco-exif-orientation-guard-omitted",
        path="training/export_detection.py",
        before=(
            "for ordinal, item in enumerate(selected, 1):\n            validate_orientation(item)"
        ),
        after="for ordinal, item in enumerate(selected, 1):\n            pass",
        case=(
            "tests/training/test_export_orientation.py::"
            "test_detection_formats_refuse_all_rotated_or_mirrored_exif_frames"
        ),
        runner="pytest",
    ),
    Mutation(
        name="training-yolo-exif-orientation-guard-omitted",
        path="training/export_detection.py",
        before='validate_image_extension(item, "yolo")\n        validate_orientation(item)',
        after='validate_image_extension(item, "yolo")\n        pass',
        case=(
            "tests/training/test_export_orientation.py::"
            "test_detection_formats_refuse_all_rotated_or_mirrored_exif_frames"
        ),
        runner="pytest",
    ),
    Mutation(
        name="training-shared-exif-orientation-guard-omitted",
        path="training/export_common.py",
        before="if image.getexif().get(274) not in (None, 1):",
        after="if False:",
        case=(
            "tests/training/test_export_orientation.py::"
            "test_detection_formats_refuse_all_rotated_or_mirrored_exif_frames"
        ),
        runner="pytest",
    ),
    Mutation(
        name="training-loader-extension-validation-omitted",
        path="training/export_common.py",
        before="if suffix not in supported:",
        after="if False and suffix not in supported:",
        case=(
            "tests/training/test_loader_extensions.py::"
            "test_imagefolder_rejects_normally_imported_gif"
        ),
        runner="pytest",
    ),
    Mutation(
        name="training-distribution-erases-measurements",
        path="ontology/training_functions.py",
        before='data=value.model_dump(mode="json"),',
        after="data={},",
        case="46-training-distribution",
    ),
    Mutation(
        name="training-leakage-erases-pairs",
        path="training/leakage.py",
        before=(
            "pairs=tuple(sorted(pairs, key=lambda pair: (pair.kind, pair.left_id, pair.right_id))),"
        ),
        after="pairs=(),",
        case="47-training-leakage",
    ),
    Mutation(
        name="training-group-boundary-ignored",
        path="training/splitting.py",
        before='if kind == "group" or request.avoid_leakage:',
        after='if kind != "group" and request.avoid_leakage:',
        case=(
            "tests/training/test_splitting.py::"
            "test_group_constraint_applies_when_duplicate_avoidance_is_disabled"
        ),
        runner="pytest",
    ),
    Mutation(
        name="training-coco-uses-xyxy-as-xywh",
        path="training/export_detection.py",
        before="bbox = (box.x1, box.y1, box.x2 - box.x1, box.y2 - box.y1)",
        after="bbox = (box.x1, box.y1, box.x2, box.y2)",
        case=(
            "tests/training/test_export.py::"
            "test_coco_standard_documents_roundtrip_absolute_boxes_and_empty_images"
        ),
        runner="pytest",
    ),
    Mutation(
        name="training-yolo-center-not-normalized",
        path="training/export_detection.py",
        before="(box.x1 + box.x2) / (2 * width)",
        after="(box.x1 + box.x2) / width",
        case="tests/training/test_export.py::test_yolo_layout_and_normalized_boxes_roundtrip",
        runner="pytest",
    ),
    Mutation(
        name="training-single-label-prevalence-constraint-omitted",
        path="training/single_prevalence.py",
        before="if labelled and count >= MIN_CATEGORY:",
        after="if labelled and count < 0:",
        case=(
            "tests/training/test_single_prevalence.py::"
            "test_integer_solver_shifts_small_totals_to_the_nearest_feasible_allocation"
        ),
        runner="pytest",
    ),
    Mutation(
        name="training-flat-image-color-confirmation-omitted",
        path="training/leakage.py",
        before="if not _image_confirmation(",
        after="if False and not _image_confirmation(",
        case=(
            "tests/storage/test_training_store.py::"
            "test_flat_color_dhash_collision_requires_color_confirmation"
        ),
        runner="pytest",
    ),
    Mutation(
        name="training-text-line-endings-normalized",
        path="training/export_common.py",
        before='return content.decode("utf-8")',
        after='return content.decode("utf-8").replace(chr(13), "")',
        case=(
            "tests/training/test_export.py::"
            "test_text_jsonl_preserves_crlf_and_carriage_return_character_positions"
        ),
        runner="pytest",
    ),
    Mutation(
        name="training-checked-signals-omits-group",
        path="training/leakage.py",
        before='checked_signals=("exact", "image", "text", "group"),',
        after='checked_signals=("exact", "image", "text"),',
        case=(
            "tests/training/test_leakage.py::"
            "test_three_signals_emit_pairs_with_distance_and_partitions"
        ),
        runner="pytest",
    ),
    Mutation(
        name="training-primary-label-depends-on-input-order",
        path="training/splitting.py",
        before="tuple(sorted(set(sample.labels)))",
        after="sample.labels[:1]",
        case=(
            "tests/training/test_primary_labels.py::"
            "test_primary_label_order_is_canonical_and_full_annotations_are_preserved"
        ),
        runner="pytest",
    ),
)
