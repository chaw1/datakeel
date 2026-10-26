# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Require standards goldens and regressions to detect ranking and lexical-rule faults."""

from scripts.mutation_models import Mutation

STANDARD_MUTATIONS = (
    Mutation(
        name="standards-worst-table",
        path="ontology/standard_functions.py",
        before="key=lambda item: (item.compliance, item.coverage, item.key)",
        after="key=lambda item: (-item.compliance, item.coverage, item.key)",
        case="41-standard-coverage",
    ),
    Mutation(
        name="standards-confirmed-usage",
        path="ontology/standard_functions.py",
        before="if item.standard_code in codes",
        after="if False",
        case="42-standard-usage",
    ),
    Mutation(
        name="standards-prefix-recall",
        path="standards/lexical.py",
        before="elif prefix_weight := _prefix_weight(left, right):",
        after="elif prefix_weight := 0.0:",
        case=(
            "tests/standards/test_mapping_variants.py::"
            "test_prefix_rule_is_required_for_unregistered_truncation"
        ),
        runner="pytest",
    ),
    Mutation(
        name="standards-morphology-recall",
        path="standards/lexical.py",
        before="if left_roots & right_roots:",
        after="if False:",
        case=(
            "tests/standards/test_mapping_variants.py::"
            "test_morphology_rule_is_required_for_irregular_payment"
        ),
        runner="pytest",
    ),
    Mutation(
        name="standards-spelling-recall",
        path="standards/lexical.py",
        before="elif _spelled_forms(left_roots) & _spelled_forms(right_roots):",
        after="elif False:",
        case=(
            "tests/standards/test_mapping_variants.py::"
            "test_spelling_rule_is_required_for_british_colour"
        ),
        runner="pytest",
    ),
    Mutation(
        name="standards-consonant-recall",
        path="standards/lexical.py",
        before="elif consonant_weight := _consonant_weight(left, right):",
        after="elif consonant_weight := 0.0:",
        case=(
            "tests/standards/test_mapping_variants.py::"
            "test_consonant_rule_is_required_for_supplier_skeleton"
        ),
        runner="pytest",
    ),
    Mutation(
        name="standards-contract-synonym-recall",
        path="standards/matching.py",
        before="expanded, synonym_reasons = _synonyms(observed, contract.synonyms)",
        after="expanded, synonym_reasons = observed, ()",
        case=(
            "tests/standards/test_mapping_variants.py::"
            "test_synonym_rule_is_required_for_contract_extension"
        ),
        runner="pytest",
    ),
    Mutation(
        name="standards-synonym-discount",
        path="standards/matching.py",
        before="score=evidence.score * 0.86,",
        after="score=evidence.score,",
        case=(
            "tests/standards/test_mapping_variants.py::"
            "test_synonym_weight_stays_below_an_exact_business_name"
        ),
        runner="pytest",
    ),
    Mutation(
        name="standards-generic-abstention",
        path="standards/matching.py",
        before="_GENERIC = frozenset(",
        after="_GENERIC = frozenset() if True else frozenset(",
        case=(
            "tests/standards/test_mapping_variants.py::"
            "test_generic_guard_rejects_a_custom_exact_generic_standard"
        ),
        runner="pytest",
    ),
    Mutation(
        name="standards-system-abstention",
        path="standards/matching.py",
        before="_SYSTEM = frozenset(",
        after="_SYSTEM = frozenset() if True else frozenset(",
        case=(
            "tests/standards/test_mapping_variants.py::"
            "test_system_guard_overrides_an_exact_business_named_system_standard"
        ),
        runner="pytest",
    ),
    Mutation(
        name="standards-retain-partial-top-three",
        path="standards/mapping.py",
        before="if lexical.score <= 0:",
        after="if lexical.score < SUGGESTION_THRESHOLD:",
        case=(
            "tests/standards/test_mapping_variants.py::"
            "test_partial_business_hit_keeps_three_low_confidence_candidates"
        ),
        runner="pytest",
    ),
    Mutation(
        name="standards-label-low-confidence",
        path="standards/mapping.py",
        before="low_confidence = score < SUGGESTION_THRESHOLD",
        after="low_confidence = False",
        case=(
            "tests/standards/test_mapping_variants.py::"
            "test_partial_business_hit_keeps_three_low_confidence_candidates"
        ),
        runner="pytest",
    ),
    Mutation(
        name="standards-system-word-variants",
        path="standards/matching.py",
        before="any(_system_variant(token) for token in tokens)",
        after="False",
        case=(
            "tests/standards/test_mapping_system_variants.py::"
            "test_complete_version_skeleton_overrides_a_business_prefix"
        ),
        runner="pytest",
    ),
    Mutation(
        name="standards-contextual-measure-suffix",
        path="standards/matching.py",
        before="_CONTEXTUAL = frozenset(",
        after="_CONTEXTUAL = frozenset() if True else frozenset(",
        case=(
            "tests/standards/test_mapping_system_variants.py::"
            "test_business_meaning_outweighs_a_shared_measure_suffix"
        ),
        runner="pytest",
    ),
    Mutation(
        name="standards-chinese-system-boundary",
        path="standards/names.py",
        before='"版本": "version",',
        after='"版本": "edition",',
        case=(
            "tests/standards/test_mapping_system_variants.py::"
            "test_chinese_system_words_override_customer_business_prefix"
        ),
        runner="pytest",
    ),
)
