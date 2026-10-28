# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Metric morphology regressions detect ambiguous selection and unsafe phrase expansion."""

from scripts.mutation_models import Mutation

METRIC_MUTATIONS = (
    Mutation(
        name="knowledge-metric-name-alias-collision",
        path="ask/knowledge_subjects.py",
        before="(2, metric.synonyms),",
        after="(1, metric.synonyms),",
        case=(
            "tests/ask/test_knowledge_metric_tiers.py::"
            "test_english_name_and_alias_owner_conflict_returns_persisted_clarification"
        ),
        runner="pytest",
    ),
    Mutation(
        name="metric-person-before-scalar",
        path="ask/knowledge_routing.py",
        before="if text_without_names != question and _requested_person(text_without_names):",
        after="if False:",
        case=(
            "tests/ask/test_numeric_person_guard.py::"
            "test_person_ownership_cannot_be_overridden_by_ranking_or_value_requests"
        ),
        runner="pytest",
    ),
    Mutation(
        name="metric-registered-name-alias-collision",
        path="ask/resolution.py",
        before='"synonym": 3',
        after='"synonym": 2',
        case=(
            "tests/ask/test_metric_english.py::"
            "test_registered_english_name_and_synonym_collision_requires_clarification"
        ),
        runner="pytest",
    ),
    Mutation(
        name="metric-id-normalization",
        path="ask/matching.py",
        before="hits = list(re.finditer(_identifier_pattern(metric.id), question, re.IGNORECASE))",
        after="hits = []",
        case=(
            "tests/ask/test_metric_english.py::"
            "test_normalized_english_owner_focus_and_metric_value_use_separate_routes"
        ),
        runner="pytest",
    ),
    Mutation(
        name="metric-normalization-collision",
        path="ask/resolution.py",
        before="if len(candidates) > 1:",
        after="if False:",
        case=(
            "tests/ask/test_metric_english.py::"
            "test_id_normalization_collision_lists_every_candidate"
        ),
        runner="pytest",
    ),
    Mutation(
        name="metric-id-word-boundary",
        path="ask/matching.py",
        before='return r"(?<![A-Za-z0-9_])" + r"[_\\-\\s]+".join(tokens) + r"(?![A-Za-z0-9_])"',
        after='return r"(?<![A-Za-z0-9_])" + r"[_\\-\\s]+".join(tokens) + r"(?![A-Za-z0-9])"',
        case=(
            "tests/ask/test_metric_english.py::"
            "test_normalized_identifiers_keep_ascii_word_boundaries"
        ),
        runner="pytest",
    ),
    Mutation(
        name="metric-normalization-before-prefix",
        path="ask/resolution.py",
        before='"normalized": 2',
        after='"normalized": 0',
        case=(
            "tests/ask/test_metric_english.py::test_normalized_id_outranks_conservative_name_prefix"
        ),
        runner="pytest",
    ),
)
