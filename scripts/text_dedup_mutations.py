# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Protect existing document identity and representative semantics from training changes."""

from scripts.mutation_models import Mutation

TEXT_DEDUP_MUTATIONS = (
    Mutation(
        name="text-dedup-casefold-identity",
        path="operators/text/dedup.py",
        before='read_text(encoding="utf-8").casefold().split()',
        after='read_text(encoding="utf-8").split()',
        case=(
            "tests/operators/test_text_dedup_compatibility.py::"
            "test_exact_only_preserves_punctuation_and_width_but_folds_case_and_whitespace"
        ),
        runner="pytest",
    ),
    Mutation(
        name="text-dedup-token-overlap",
        path="operators/text/dedup.py",
        before="len(tokens & prior) / len(tokens | prior) >= params.threshold",
        after="False",
        case=(
            "tests/operators/test_text_dedup_compatibility.py::"
            "test_approximate_documents_use_token_sets_regardless_of_word_order"
        ),
        runner="pytest",
    ),
    Mutation(
        name="text-dedup-retained-representatives",
        path="operators/text/dedup.py",
        before="        if duplicate:\n            issues.append",
        after=(
            "        if duplicate:\n            token_sets.append(tokens)\n"
            "            issues.append"
        ),
        case=(
            "tests/operators/test_text_dedup_compatibility.py::"
            "test_approximate_documents_only_compare_against_retained_representatives"
        ),
        runner="pytest",
    ),
)
