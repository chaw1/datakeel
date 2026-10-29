# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Measure independent training parser, cleaning, language and contamination guards."""

from scripts.mutation_models import Mutation

LLM_DATA_MUTATIONS = (
    Mutation(
        name="training-code-fence-truncation",
        path="llm_data/checks.py",
        before="    return opened is not None",
        after="    return False",
        case=(
            "tests/llm_data/test_checks.py::"
            "test_code_fence_when_tilde_block_is_unclosed_reports_truncation"
        ),
        runner="pytest",
    ),
    Mutation(
        name="training-invalid-preview-privacy",
        path="llm_data/engine.py",
        before='        preview="[UNPARSEABLE_RECORD]",',
        after='        preview=redact_pii(line.raw.decode("utf-8", errors="replace")),',
        case=(
            "tests/llm_data/test_engine.py::"
            "test_invalid_record_never_exposes_encoded_or_partial_private_payload"
        ),
        runner="pytest",
    ),
    Mutation(
        name="training-blocking-clean-decision",
        path="llm_data/engine.py",
        before="    if codes & _BLOCKING:",
        after="    if False:",
        case="tests/llm_data/test_engine.py::test_dry_run_ledger_cleans_redacts_and_explains_every_record",
        runner="pytest",
    ),
    Mutation(
        name="training-preference-identity",
        path="llm_data/engine.py",
        before='    if parsed.format != "preference":',
        after="    if True:",
        case="tests/llm_data/test_similarity.py::test_preference_identical_and_near_identical_are_always_reported",
        runner="pytest",
    ),
    Mutation(
        name="training-lightly-edited-contamination",
        path="llm_data/contamination.py",
        before="        if not (exact or contained or fuzzy):",
        after="        if not exact:",
        case="tests/llm_data/test_contamination.py::test_short_lightly_edited_question_uses_conservative_fallback",
        runner="pytest",
    ),
    Mutation(
        name="training-native-fingerprint-parity",
        path="llm_data/acceleration.py",
        before="        return hashed, tuple(",
        after="        return hashed ^ 1, tuple(",
        case=(
            "tests/llm_data/test_acceleration.py::"
            "test_native_fingerprint_when_unicode_and_feature_sampling_vary_matches_every_byte"
        ),
        runner="pytest",
    ),
    Mutation(
        name="training-native-band-width",
        path="llm_data/acceleration.py",
        before="        if len(packed) != _BAND_COUNT * _BAND_BYTES:",
        after="        if False:",
        case=(
            "tests/llm_data/test_acceleration.py::"
            "test_native_band_width_when_invalid_is_rejected_with_a_typed_error"
        ),
        runner="pytest",
    ),
    Mutation(
        name="training-native-similarity-parity",
        path="llm_data/acceleration.py",
        before="        return dice(blobs(left), blobs(right))",
        after="        return 0",
        case=(
            "tests/llm_data/test_acceleration.py::"
            "test_native_similarity_when_lengths_and_scripts_vary_matches_python_float_bits"
        ),
        runner="pytest",
    ),
)
