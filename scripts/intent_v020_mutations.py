# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""v0.20.0 anchors: one-sentence plans follow the v0.19.0 work rules and prompt budget."""

from scripts.mutation_models import Mutation

_T = "tests/intents/test_work_rules_v020.py::"


def _anchor(name: str, path: str, change: tuple[str, str], case: str) -> Mutation:
    before, after = change
    return Mutation(
        name=f"v020-{name}", path=path, before=before, after=after, case=case, runner="pytest"
    )


INTENT_V020_MUTATIONS = (
    _anchor(
        "a-dispatch-fits-the-per-person-limit",
        "intents/preconditions.py",
        ("    if load + adding <= limit:", "    if True:"),
        _T + "test_a_dispatch_over_the_per_person_limit_is_said_before_a_card",
    ),
    _anchor(
        "a-dispatch-only-lowers-the-limit",
        "intents/preconditions.py",
        (
            "    if target.limit is not None and setting is not None and target.limit > setting:",
            "    if False:",
        ),
        _T + "test_a_dispatch_never_raises_the_project_limit",
    ),
    _anchor(
        "review-skips-everyone-who-annotated",
        "storage/intent_reads.py",
        (
            "            and person in annotators(session, row)",
            "            and person == row.annotator_id",
        ),
        _T + "test_review_never_goes_back_to_an_annotator_after_a_rework_handover",
    ),
    _anchor(
        "a-template-upgrade-needs-a-newer-version",
        "intents/preconditions.py",
        (
            '    "upgrade_project_template": ("finalized", "upgradable"),',
            '    "upgrade_project_template": ("finalized",),',
        ),
        _T + "test_a_template_upgrade_needs_a_newer_version_to_move_to",
    ),
)
