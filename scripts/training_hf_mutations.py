# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Hugging Face metadata links, review states and counters have independent measured anchors."""

from scripts.mutation_models import Mutation

HF_TRAINING_MUTATIONS = (
    Mutation(
        name="training-hf-labels-erased",
        path="training/export_hf.py",
        before="labels_json=json_text(item.annotation.labels),",
        after="labels_json=json_text(None),",
        case=(
            "tests/training/test_export_hf.py::"
            "test_hf_metadata_preserves_original_annotations_and_empty_review_states"
        ),
        runner="pytest",
    ),
    Mutation(
        name="training-hf-reviewed-empty-boxes-become-missing",
        path="training/export_hf.py",
        before='None if boxes is None else [box.model_dump(mode="json") for box in boxes]',
        after='None if not boxes else [box.model_dump(mode="json") for box in boxes]',
        case=(
            "tests/training/test_export_hf.py::"
            "test_hf_metadata_preserves_original_annotations_and_empty_review_states"
        ),
        runner="pytest",
    ),
    Mutation(
        name="training-hf-metadata-link-adds-split-twice",
        path="training/export_hf.py",
        before="file_name=name,",
        after='file_name=f"{split}/{name}",',
        case=(
            "tests/training/test_export_hf.py::"
            "test_hf_metadata_file_names_are_safe_relative_links_to_unchanged_images"
        ),
        runner="pytest",
    ),
    Mutation(
        name="training-hf-annotation-count-omits-boxes",
        path="training/export.py",
        before=(
            'if format_name == "hf_imagefolder":\n'
            "        return len(item.annotation.labels or ()) + len(item.annotation.boxes or ())"
        ),
        after=(
            'if format_name == "hf_imagefolder":\n        return len(item.annotation.labels or ())'
        ),
        case=(
            "tests/training/test_export_hf.py::"
            "test_hf_archive_manifest_counts_labels_and_boxes_and_reproduces_bytes"
        ),
        runner="pytest",
    ),
    Mutation(
        name="training-hf-loader-extension-guard-omitted",
        path="training/export_hf.py",
        before='validate_image_extension(item, "hf_imagefolder")',
        after="pass",
        case=(
            "tests/training/test_export_hf.py::"
            "test_hf_loader_unsupported_extension_is_explicitly_rejected"
        ),
        runner="pytest",
    ),
    Mutation(
        name="training-hf-loader-exif-orientation-guard-omitted",
        path="training/export_hf.py",
        before="            write_image(item, geometry, directory / relative)",
        after=(
            '            write_image(item, geometry.model_copy(update={"orientation": 1}), '
            "directory / relative)"
        ),
        case=(
            "tests/training/test_export_hf.py::"
            "test_hf_loader_exif_rotation_and_mirroring_are_written_upright"
        ),
        runner="pytest",
    ),
)
