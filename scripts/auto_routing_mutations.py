# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Measure independent automatic image routing signals against generated fixtures."""

from scripts.mutation_models import Mutation

_TESTS = "tests/transcription/test_auto_rules.py::"

AUTO_ROUTING_MUTATIONS = (
    Mutation(
        name="auto-low-confidence-disabled",
        path="transcription/auto.py",
        before="if confidence < config.min_mean_confidence:",
        after="if False:",
        case=_TESTS + "test_low_confidence_below_threshold_routes_to_vision[0.1]",
        runner="pytest",
    ),
    Mutation(
        name="auto-structure-disabled",
        path="transcription/auto.py",
        before="if _ARROW.search(ocr.text) or _has_structure(ink, boxes, config):",
        after="if False:",
        case=_TESTS + "test_structure_diagram_connected_labels_routes_to_vision[arrow]",
        runner="pytest",
    ),
    Mutation(
        name="auto-row-state-disabled",
        path="transcription/auto.py",
        before="if has_strike(pixels, boxes, config) or has_grey_row(pixels, boxes, config):",
        after="if False:",
        case=_TESTS + "test_struck_rows_long_central_stroke_routes_to_vision[1.0]",
        runner="pytest",
    ),
    Mutation(
        name="auto-sparse-text-disabled",
        path="transcription/auto.py",
        before="if _is_sparse(pixels, ink, boxes, characters, config, document_area):",
        after="if False:",
        case=_TESTS + "test_sparse_text_oversized_recognition_box_routes_to_vision",
        runner="pytest",
    ),
    Mutation(
        name="auto-ocr-error-ignored",
        path="transcription/auto.py",
        before="        or ocr.error\n",
        after="        or False\n",
        case=_TESTS + "test_ocr_failed_missing_attempt_or_output_has_reason[error]",
        runner="pytest",
    ),
    Mutation(
        name="auto-clean-reason-corrupted",
        path="transcription/auto.py",
        before='reasons=tuple(reasons) or ("clean_text",)',
        after='reasons=tuple(reasons) or ("sparse_text",)',
        case=(
            _TESTS + "test_clean_text_generated_document_stays_local"
            "[UPPERCASE REGISTER WITH NORMAL ROW SPACING]"
        ),
        runner="pytest",
    ),
    Mutation(
        name="auto-cache-policy-omitted",
        path="transcription/cache.py",
        before='if (mode or profile.mode) != "auto":',
        after="if True:",
        case="tests/actions/test_auto_fingerprints.py::"
        "test_auto_profile_and_cache_include_every_rule_field[min_mean_confidence]",
        runner="pytest",
    ),
    Mutation(
        name="auto-native-ocr-failure-unwrapped",
        path="transcription/ocr.py",
        before='raise TranscriptionUnavailableError(message, reason="provider_error") from error',
        after="raise",
        case="tests/transcription/test_auto_adapter_review.py::"
        "test_auto_runtime_ocr_failure_does_not_abort_remaining_images",
        runner="pytest",
    ),
)
