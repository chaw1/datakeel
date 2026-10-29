# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Assert that text formatting invariance and measured similarity edges cannot regress."""

from scripts.mutation_models import Mutation

TRAINING_TEXT_MUTATIONS = (
    Mutation(
        name="training-exact-text-is-not-reported-again-as-near",
        path="training/leakage.py",
        before=(
            "if left_sample.file.sha256 and left_sample.file.sha256 == right_sample.file.sha256:"
        ),
        after="if False:",
        case=(
            "tests/training/test_leakage.py::"
            "test_byte_identical_text_has_one_exact_pair_without_a_second_text_pair"
        ),
        runner="pytest",
    ),
    Mutation(
        name="training-text-zero-width-normalization",
        path="training/text_hashes.py",
        before="and character not in _ZERO_WIDTH",
        after="and True",
        case=(
            "tests/training/test_text_hashes.py::"
            "test_zero_width_formatting_cannot_hide_an_identical_text"
        ),
        runner="pytest",
    ),
    Mutation(
        name="training-text-signal-omitted",
        path="training/leakage.py",
        before="yield from _text_pairs(samples, request.text_threshold)",
        after="yield from _text_pairs((), request.text_threshold)",
        case=(
            "tests/training/test_leakage.py::"
            "test_three_signals_emit_pairs_with_distance_and_partitions"
        ),
        runner="pytest",
    ),
    Mutation(
        name="training-text-uses-lossy-prefix-blocking",
        path="training/leakage.py",
        before='threshold=threshold, mode="exact")',
        after='threshold=threshold, mode="prefix")',
        case=(
            "tests/training/test_leakage.py::"
            "test_text_threshold_is_inclusive_and_prefix_boundaries_are_lossless"
        ),
        runner="pytest",
    ),
    Mutation(
        name="training-text-threshold-widened",
        path="training/leakage.py",
        before="yield from _text_pairs(samples, request.text_threshold)",
        after="yield from _text_pairs(samples, request.text_threshold + 1)",
        case=(
            "tests/training/test_leakage.py::"
            "test_text_threshold_is_inclusive_and_prefix_boundaries_are_lossless"
        ),
        runner="pytest",
    ),
    Mutation(
        name="training-text-casefold-omitted",
        path="training/text_hashes.py",
        before=".casefold()",
        after="",
        case=(
            "tests/training/test_text_hashes.py::"
            "test_formatting_variants_have_identical_normalized_text_and_hash"
        ),
        runner="pytest",
    ),
    Mutation(
        name="training-text-whitespace-retained",
        path="training/text_hashes.py",
        before="if not character.isspace()",
        after="if True",
        case=(
            "tests/training/test_text_hashes.py::"
            "test_formatting_variants_have_identical_normalized_text_and_hash"
        ),
        runner="pytest",
    ),
    Mutation(
        name="training-text-unicode-punctuation-retained",
        path="training/text_hashes.py",
        before='and not unicodedata.category(character).startswith("P")',
        after="and True",
        case=(
            "tests/training/test_text_hashes.py::"
            "test_formatting_variants_have_identical_normalized_text_and_hash"
        ),
        runner="pytest",
    ),
    Mutation(
        name="training-text-compatibility-normalization-omitted",
        path="training/text_hashes.py",
        before='unicodedata.normalize("NFKC", unicodedata.normalize("NFKC", text).casefold())',
        after="text.casefold()",
        case=(
            "tests/training/test_text_hashes.py::"
            "test_formatting_variants_have_identical_normalized_text_and_hash"
        ),
        runner="pytest",
    ),
    Mutation(
        name="training-text-joined-combining-sequence-not-normalized",
        path="training/text_hashes.py",
        before='return unicodedata.normalize("NFKC", characters)',
        after="return characters",
        case=(
            "tests/training/test_text_hashes.py::"
            "test_removing_formatting_recomposes_combining_characters_idempotently"
        ),
        runner="pytest",
    ),
    Mutation(
        name="training-text-empty-collides",
        path="training/text_hashes.py",
        before="if not normalized:\n        return None",
        after="if not normalized:\n        return 0",
        case=(
            "tests/training/test_text_hashes.py::"
            "test_empty_punctuation_has_no_similarity_signal_and_short_text_uses_one_feature"
        ),
        runner="pytest",
    ),
    Mutation(
        name="training-text-feature-frequency-ignored",
        path="training/text_hashes.py",
        before="votes[bit] += weight if fingerprint & (1 << bit) else -weight",
        after="votes[bit] += 1 if fingerprint & (1 << bit) else -1",
        case=(
            "tests/training/test_text_hashes.py::"
            "test_simhash_stable_fingerprint_keeps_feature_multiplicities_and_zero_ties"
        ),
        runner="pytest",
    ),
    Mutation(
        name="training-text-zero-vote-set",
        path="training/text_hashes.py",
        before="if vote > 0)",
        after="if vote >= 0)",
        case=(
            "tests/training/test_text_hashes.py::"
            "test_simhash_stable_fingerprint_keeps_feature_multiplicities_and_zero_ties"
        ),
        runner="pytest",
    ),
)
