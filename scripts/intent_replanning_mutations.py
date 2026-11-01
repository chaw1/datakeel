# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Anchors for explicit deferred suffixes and replanning against the new state."""

from scripts.mutation_models import Mutation

_M = "tests/intents/test_claim_chain_matrix.py::"


def _anchor(name: str, path: str, change: tuple[str, str], case: str) -> Mutation:
    before, after = change
    return Mutation(
        name=f"replanning-{name}",
        path=path,
        before=before,
        after=after,
        case=_M + case,
        runner="pytest",
    )


def _barrier(case: str) -> Mutation:
    return _anchor(
        f"safe-prefix-{case}",
        "intents/replanning.py",
        (
            "    if deferred and (narrowed := without(draft, deferred)) is not None:",
            "    if False and (narrowed := without(draft, deferred)) is not None:",
        ),
        f"test_defer_then_replan_matrix[{case}]",
    )


REPLANNING_MUTATIONS = (
    _barrier("claim-claim-over"),
    _barrier("claim-release-claim"),
    _anchor(
        "dependent-suffix-is-deferred",
        "intents/replanning.py",
        ("        if dependent:", "        if False:"),
        "test_defer_then_replan_matrix[release-release]",
    ),
    _anchor(
        "different-projects-stay-independent",
        "intents/replanning.py",
        (
            "                or projects[previous] == projects[index]",
            "                or True",
        ),
        "test_defer_then_replan_matrix[project-isolation]",
    ),
    _anchor(
        "deferred-steps-stay-in-chain-notes",
        "intents/resolve.py",
        (
            "                    *skipped_lines(draft.skipped, text, draft.language),",
            "                    *(),",
        ),
        "test_deferred_note_is_explicit_in_english",
    ),
    _anchor(
        "english-result-says-deferred",
        "intents/replanning.py",
        (
            '"deferred for replanning"',
            '"try again"',
        ),
        "test_deferred_note_is_explicit_in_english",
    ),
)
