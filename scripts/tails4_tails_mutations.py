# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""TAILS-4 interface tails: English answer wording and the assignee read tool."""

from scripts.mutation_models import Mutation

_EN = "tests/ask/test_interpretation_en.py::"

TAILS_MUTATIONS = (
    Mutation(
        name="ask-english-interpretation-metric-name",
        path="ask/interpretation_en.py",
        before='parts = [f"Query {card.definition.english_name or card.definition.name}"]',
        after='parts = [f"Query {card.definition.name}"]',
        case=_EN + "test_english_interpretation_words_every_slot_with_registered_english_names",
        runner="pytest",
    ),
    Mutation(
        name="ask-english-interpretation-dimension-name",
        path="ask/interpretation_en.py",
        before="names = {item.id: item.english_name or item.name for item in layer.dimensions}",
        after="names = {item.id: item.name for item in layer.dimensions}",
        case=_EN + "test_english_interpretation_words_every_slot_with_registered_english_names",
        runner="pytest",
    ),
    Mutation(
        name="ask-english-interpretation-previous-period",
        path="ask/interpretation_en.py",
        before='if frame.comparison == "year_over_year"',
        after="if frame.comparison",
        case=_EN + "test_english_interpretation_of_shares_and_previous_periods",
        runner="pytest",
    ),
    Mutation(
        name="ask-subject-english-name",
        path="ask/knowledge_subjects.py",
        before="english_name=item.english_name,",
        after="english_name=None,",
        case=_EN + "test_recognized_metric_subject_carries_its_registered_english_name",
        runner="pytest",
    ),
)
