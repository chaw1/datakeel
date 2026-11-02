# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Targeted native-segment behavior anchors; full-catalog shards include these in CI."""

from scripts.mutation_models import Mutation

_CORE = "tests/core/test_segments.py::"
_STORAGE = "tests/storage/test_production_segments.py::"
_CONTEXT = "tests/storage/test_segment_training_context.py::"
_EXPORT = "tests/training/test_segment_export.py::"
_METRICS = "tests/annotation_qa/test_segment_metrics.py::"

SEGMENT_MUTATIONS = (
    Mutation(
        name="segment-strict-int-becomes-coercive",
        path="core/annotation_models.py",
        before="    start_ms: StrictInt = Field(ge=0)",
        after="    start_ms: int = Field(ge=0)",
        case=_CORE + "test_segment_milliseconds_require_real_integers[True]",
        runner="pytest",
    ),
    Mutation(
        name="segment-duration-drift-accepted",
        path="core/production_segments.py",
        before="    if annotation.media_duration_ms != probe.duration_ms:",
        after="    if False:",
        case=_CORE + "test_source_duration_must_match_exactly[3249]",
        runner="pytest",
    ),
    Mutation(
        name="segment-project-skips-source-probes",
        path="storage/production_projects.py",
        before='        if "segment" in enabled_components(template):',
        after="        if False:",
        case=_STORAGE + "test_project_creation_checks_every_source_even_without_revisions",
        runner="pytest",
    ),
    Mutation(
        name="segment-upgrade-skips-source-probes",
        path="storage/production_template_upgrade.py",
        before='        if "segment" in enabled_components(after):',
        after="        if False:",
        case=_STORAGE + "test_template_upgrade_checks_unprobed_sources_before_impact_plan",
        runner="pytest",
    ),
    Mutation(
        name="segment-native-import-skips-media-validation",
        path="storage/annotation_store.py",
        before="    _validate_segments(version, request.batch)",
        after="    request.batch",
        case=_STORAGE + "test_native_import_rejects_bad_media_before_batch_insert",
        runner="pytest",
    ),
    Mutation(
        name="segment-lossy-format-filtered-before-rejection",
        path="storage/training_export.py",
        before=(
            "        require_no_segments(\n"
            "            (record for member in split.members for record in member.annotations), "
            "params.format\n"
            "        )"
        ),
        after="        require_no_segments((), params.format)",
        case=_CONTEXT + "test_prepare_rejects_all_frozen_segment_records_before_audio_filter",
        runner="pytest",
    ),
    Mutation(
        name="segment-webvtt-unreviewed-becomes-empty",
        path="training/export_segments.py",
        before=(
            "    if annotation.segments is None:\n"
            '        message = f"WebVTT requires reviewed segments for {item.file.id}; '
            'unreviewed is not empty"\n'
            "        raise ValidationError(message)\n"
            "    validate_segment_media(item.file, annotation)"
        ),
        after=(
            "    annotation = annotation.model_copy("
            'update={"segments": annotation.segments or ()})\n'
            "    validate_segment_media(item.file, annotation)"
        ),
        case=_EXPORT + "test_webvtt_rejects_unreviewed_instead_of_emitting_negative",
        runner="pytest",
    ),
    Mutation(
        name="segment-mixed-metrics-false-perfect-score",
        path="annotation_qa/prelabel_match.py",
        before="    if model.segments is not None or human.segments is not None:",
        after="    if False:",
        case=_METRICS + "test_mixed_classification_cannot_hide_segments_behind_perfect_agreement",
        runner="pytest",
    ),
    Mutation(
        name="segment-classification-inflates-max-count",
        path="storage/production_catalog.py",
        before=(
            "    count = (\n"
            "        len(annotation.segments or ())\n"
            '        if "segment" in enabled\n'
            "        else sum(len(content[kind] or ()) for kind in enabled)\n"
            "    )"
        ),
        after="    count = sum(len(content[kind] or ()) for kind in enabled)",
        case=_STORAGE + "test_max_one_allows_one_segment_with_classification",
        runner="pytest",
    ),
    Mutation(
        name="segment-classification-fills-min-count",
        path="storage/production_catalog.py",
        before=(
            "    count = (\n"
            "        len(annotation.segments or ())\n"
            '        if "segment" in enabled\n'
            "        else sum(len(content[kind] or ()) for kind in enabled)\n"
            "    )"
        ),
        after="    count = sum(len(content[kind] or ()) for kind in enabled)",
        case=_STORAGE + "test_min_two_rejects_one_segment_with_classification",
        runner="pytest",
    ),
)
