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
        before=(
            "expanded, reasons, weight = "
            "_synonyms(observed, contract.synonyms, _Lock(complete, kin))"
        ),
        after="expanded, reasons, weight = observed, (), 1.0",
        case=(
            "tests/standards/test_mapping_variants.py::"
            "test_synonym_rule_is_required_for_contract_extension"
        ),
        runner="pytest",
    ),
    Mutation(
        name="standards-synonym-discount",
        path="standards/matching.py",
        before="_SYNONYM_DISCOUNT = 0.86",
        after="_SYNONYM_DISCOUNT = 1.0",
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

DELETIONS = "tests/standards/test_mapping_deletions.py::"
LIFECYCLE = "tests/standards/test_mapping_lifecycle_synonyms.py::"
PRIORITY = "tests/standards/test_mapping_priority.py::"

# Lexical recall rules and the precision guards that bound them.
LEXICAL_RULE_MUTATIONS = (
    Mutation(
        name="standards-deletion-recall",
        path="standards/lexical.py",
        before="elif deletion_weight := _deletion_weight(left, right):",
        after="elif deletion_weight := 0.0:",
        case=DELETIONS + "test_deletion_rule_is_required_for_unregistered_channel",
        runner="pytest",
    ),
    Mutation(
        name="standards-deletion-vowel-join",
        path="standards/lexical.py",
        before="or not _joins_consonants(observed, expected)",
        after="or False",
        case=DELETIONS + "test_deletion_requires_a_dropped_vowel_between_kept_consonants",
        runner="pytest",
    ),
    Mutation(
        name="standards-deletion-coverage",
        path="standards/lexical.py",
        before="_MIN_DELETION_COVERAGE = 0.75",
        after="_MIN_DELETION_COVERAGE = 0.5",
        case=DELETIONS + "test_deletion_requires_most_consonants",
        runner="pytest",
    ),
    Mutation(
        name="standards-deletion-below-prefix",
        path="standards/lexical.py",
        before="return 0.5 + 0.14 * coverage",
        after="return 0.9 + 0.05 * coverage",
        case=DELETIONS + "test_deletion_ranks_below_prefix_and_consonant_skeleton",
        runner="pytest",
    ),
    Mutation(
        name="standards-audit-modified-verb",
        path="standards/matching.py",
        before='"modified",',
        after="",
        case=LIFECYCLE + "test_modified_audit_date_is_not_an_order_date",
        runner="pytest",
    ),
    Mutation(
        name="standards-audit-author-suffix",
        path="standards/matching.py",
        before='"on", "by", "last"',
        after='"on", "last"',
        case=LIFECYCLE + "test_audit_author_suffix_blocks_business_prefix",
        runner="pytest",
    ),
    Mutation(
        name="standards-complete-word-lock",
        path="standards/matching.py",
        before=(
            "and (match.rule in COMPLETE_RULES or left not in lock.tokens "
            "or (left, right) in lock.kin)"
        ),
        after="and True",
        case=(
            PRIORITY + "test_complete_word_is_never_reread_as_abbreviation_of_another_meaning"
            "[port-harbor-portfolio-label]"
        ),
        runner="pytest",
    ),
    Mutation(
        name="standards-own-group-abbreviation",
        path="standards/matching.py",
        before="kin = _kin(complete, contract.synonyms)",
        after="kin: frozenset[tuple[str, str]] = frozenset()",
        case=PRIORITY + "test_word_may_abbreviate_a_word_of_its_own_synonym_group",
        runner="pytest",
    ),
    Mutation(
        name="standards-closest-partial-synonym",
        path="standards/matching.py",
        before="hits.sort(key=lambda hit: (-len(hit[0]), -min(item.weight for item in hit[0])))",
        after="hits.sort(key=lambda hit: -len(hit[0]))",
        case=PRIORITY + "test_closest_partial_synonym_wins_over_a_longer_listing",
        runner="pytest",
    ),
    Mutation(
        name="standards-partial-ceiling",
        path="standards/lexical.py",
        before="_PARTIAL_CEILING = 0.85",
        after="_PARTIAL_CEILING = 0.95",
        case=PRIORITY + "test_partial_rules_never_reach_the_complete_synonym_weight",
        runner="pytest",
    ),
)
