# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Upright image frame: geometry, served pixels, legacy reads, imports and exports."""

from scripts.mutation_models import Mutation

_CORE = "tests/core/test_image_orientation.py::"
_RECORDS = "tests/storage/test_orientation_records.py::"
_DATASETS = "tests/storage/test_orientation_datasets.py::"
_EXPORT = "tests/training/test_export_upright.py::"
_EVERY = _EXPORT + "test_every_exif_orientation_exports_pixels_and_boxes_in_one_upright_frame"
_UNROTATED = "geometry.model_copy(update={'orientation': 1})"
_IMAGEFOLDER = _EXPORT + "test_classification_imagefolder_is_upright_for_a_loader_that_ignores_exif"
_UPGRADE = (
    "tests/evidence/test_execution.py::"
    "test_upgrade_re_extracts_stored_frame_boxes_instead_of_reusing_v0_18_cache"
)

ORIENTATION_MUTATIONS = (
    Mutation(
        name="orientation-rotate-270-point-map",
        path="core/image_orientation.py",
        before="        6: (height - y, x),\n",
        after="        6: (y, width - x),\n",
        case=_CORE + "test_every_stored_pixel_lands_where_pillow_puts_it[6]",
        runner="pytest",
    ),
    Mutation(
        name="orientation-mirrored-transverse-point-map",
        path="core/image_orientation.py",
        before="        7: (height - y, width - x),\n",
        after="        7: (y, x),\n",
        case=_CORE + "test_every_stored_pixel_lands_where_pillow_puts_it[7]",
        runner="pytest",
    ),
    Mutation(
        name="orientation-swapped-sizes-include-mirrors",
        path="core/image_orientation.py",
        before="_SWAPPED = frozenset({5, 6, 7, 8})",
        after="_SWAPPED = frozenset({6, 8})",
        case=_CORE + "test_every_stored_pixel_lands_where_pillow_puts_it[5]",
        runner="pytest",
    ),
    Mutation(
        name="orientation-inverted-box-stays-inverted",
        path="core/image_orientation.py",
        before="    y1, y2 = _span(first[1], second[1], ordered=y_source)",
        after="    y1, y2 = _span(first[1], second[1], ordered=True)",
        case=_CORE + "test_inverted_boxes_stay_inverted_and_unknown_size_stays_unknown",
        runner="pytest",
    ),
    Mutation(
        name="orientation-import-records-upright-size",
        path="storage/image_geometry.py",
        before='        "width": geometry.width,\n',
        after='        "width": geometry.stored_width,\n',
        case=_RECORDS + "test_import_records_upright_size_stored_size_and_orientation",
        runner="pytest",
    ),
    Mutation(
        name="orientation-older-imports-backfill-from-header",
        path="storage/image_geometry.py",
        before="        return _object_geometry(key)\n",
        after="        return None\n",
        case=_RECORDS + "test_older_imports_backfill_geometry_from_the_header",
        runner="pytest",
    ),
    Mutation(
        name="orientation-served-pixels-transposed",
        path="storage/image_geometry.py",
        before="        upright = ImageOps.exif_transpose(image)\n",
        after="        upright = image.copy()\n",
        case=_RECORDS + "test_served_canvas_and_thumbnail_match_what_a_browser_shows",
        runner="pytest",
    ),
    Mutation(
        name="orientation-legacy-revision-read-upright",
        path="storage/annotation_frames.py",
        before="    if row.coordinate_frame == DISPLAY_FRAME:\n        return revision\n",
        after="    if True:\n        return revision\n",
        case=_RECORDS + "test_legacy_stored_frame_heads_are_read_upright_on_the_same_object[6]",
        runner="pytest",
    ),
    Mutation(
        name="orientation-new-revisions-marked-upright",
        path="storage/production_revisions.py",
        before="            coordinate_frame=DISPLAY_FRAME,\n",
        after="            coordinate_frame=None,\n",
        case=_RECORDS + "test_coco_frame_follows_declared_size_and_explicit_override",
        runner="pytest",
    ),
    Mutation(
        name="orientation-coco-stored-size-means-stored-frame",
        path="storage/prediction_frames.py",
        before='        return "stored"\n',
        after='        return "display"\n',
        case=_RECORDS + "test_coco_frame_follows_declared_size_and_explicit_override",
        runner="pytest",
    ),
    Mutation(
        name="orientation-yolo-predictions-upright",
        path="storage/production_prediction_parsing.py",
        before='    frame: CoordinateFrame = file.coordinate_frame or "display"\n',
        after='    frame: CoordinateFrame = file.coordinate_frame or "stored"\n',
        case=_RECORDS + "test_square_coco_defaults_to_upright_and_yolo_is_upright",
        runner="pytest",
    ),
    Mutation(
        name="orientation-yolo-annotations-rescaled-upright",
        path="storage/prediction_frames.py",
        before="        return _rescaled(record, geometry.width, geometry.height)\n",
        after="        return record\n",
        case=_DATASETS + "test_yolo_import_is_relative_to_the_upright_image",
        runner="pytest",
    ),
    Mutation(
        name="orientation-new-batches-marked-upright",
        path="storage/annotation_store.py",
        before="            coordinate_frame=DISPLAY_FRAME,\n",
        after="            coordinate_frame=None,\n",
        case=_DATASETS + "test_yolo_import_is_relative_to_the_upright_image",
        runner="pytest",
    ),
    Mutation(
        name="orientation-legacy-batch-read-upright",
        path="storage/annotation_frames.py",
        before="    if row.coordinate_frame == DISPLAY_FRAME:\n        return batch\n",
        after="    if True:\n        return batch\n",
        case=_DATASETS + "test_legacy_batches_and_frozen_splits_are_read_upright",
        runner="pytest",
    ),
    Mutation(
        name="orientation-legacy-split-read-upright",
        path="storage/training_export.py",
        before="    if row.coordinate_frame == DISPLAY_FRAME:\n        return split\n",
        after="    if True:\n        return split\n",
        case=_DATASETS + "test_legacy_batches_and_frozen_splits_are_read_upright",
        runner="pytest",
    ),
    Mutation(
        name="orientation-export-writes-upright-pixels",
        path="training/export_common.py",
        before="    if geometry.orientation == 1:\n        copy_source(item, destination)\n",
        after="    if True:\n        copy_source(item, destination)\n",
        case=_EXPORT
        + "test_every_exif_orientation_exports_pixels_and_boxes_in_one_upright_frame[yolo]",
        runner="pytest",
    ),
    Mutation(
        name="orientation-export-upright-dimensions",
        path="training/export_common.py",
        before="    width, height = geometry.width, geometry.height\n",
        after="    width, height = geometry.stored_width, geometry.stored_height\n",
        case=_EXPORT + "test_detection_size_is_the_upright_size_for_all_eight_values",
        runner="pytest",
    ),
    Mutation(
        name="orientation-export-manifest-traces-reencoding",
        path="training/export.py",
        before="    if geometry.orientation != 1:\n",
        after="    if False:\n",
        case=_EXPORT + "test_manifest_traces_original_orientation_and_transform",
        runner="pytest",
    ),
    Mutation(
        name="orientation-evidence-boxes-upright",
        path="operators/evidence/annotation_labels.py",
        before="        return upright, geometry\n",
        after="        return upright, None\n",
        case="tests/operators/evidence/test_annotation_labels.py::"
        "test_rotated_photo_with_stored_size_sidecar_lands_in_the_upright_frame",
        runner="pytest",
    ),
    Mutation(
        name="orientation-served-jpeg-stays-jpeg",
        path="storage/image_geometry.py",
        before='        if source_format == "JPEG" and upright.mode in _JPEG_MODES:\n',
        after="        if False:\n",
        case=_RECORDS + "test_rotated_jpeg_is_served_as_upright_jpeg_and_revalidated",
        runner="pytest",
    ),
    Mutation(
        name="orientation-served-repeat-is-304",
        path="api/routes/production.py",
        before='        if request.headers.get("if-none-match") == tag:\n',
        after="        if False:\n",
        case=_RECORDS + "test_rotated_jpeg_is_served_as_upright_jpeg_and_revalidated",
        runner="pytest",
    ),
    Mutation(
        name="orientation-imagefolder-writes-upright-pixels",
        path="training/export_records.py",
        before="        write_image(item, geometry, directory / relative)\n",
        after=f"        write_image(item, {_UNROTATED}, directory / relative)\n",
        case=_IMAGEFOLDER,
        runner="pytest",
    ),
    Mutation(
        name="orientation-imagefolder-manifest-traces-transform",
        path="training/export.py",
        before='_UPRIGHT_FORMATS = frozenset({"coco", "yolo", "hf_imagefolder", "imagefolder"})',
        after='_UPRIGHT_FORMATS = frozenset({"coco", "yolo", "hf_imagefolder"})',
        case=_IMAGEFOLDER,
        runner="pytest",
    ),
    Mutation(
        name="orientation-phash-version-retires-v0-18-cache",
        path="operators/evidence/image_phash.py",
        before='VERSION = "1.1"\n',
        after='VERSION = "1.0"\n',
        case=_UPGRADE,
        runner="pytest",
    ),
    Mutation(
        name="orientation-labels-version-retires-v0-18-cache",
        path="operators/evidence/annotation_labels.py",
        before='VERSION = "1.1"\n',
        after='VERSION = "1.0"\n',
        case=_UPGRADE,
        runner="pytest",
    ),
)
