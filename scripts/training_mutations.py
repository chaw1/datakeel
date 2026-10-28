# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Measure independent training parser, cleaning, language and contamination guards."""

from scripts.mutation_models import Mutation

TRAINING_MUTATIONS = (
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
)
