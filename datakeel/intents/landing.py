# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Before a sentence ends as "the platform has no such feature", the flow checks once.

A model may answer that nothing fits although one registered action does what was asked,
only without a value, with an unclear object or beyond the speaker's rights. That action
("fits", or the single name in "choose") is planned like any other step: the speaker's
permission is checked first (a refusal with the reason), then every missing or unclear value
becomes a question with choices. Only when no registered action does it does the person hear
that the feature is missing, with close things the platform can do.
"""

from datakeel.intents.drafts import DraftStep, IntentDraft
from datakeel.intents.rules import full_registry
from datakeel.ontology.functions import PARAMETER_MODELS


def _registered() -> set[str]:
    registry = full_registry()
    return {entry.id for entry in [*registry.actions, *registry.functions]}


def fitting_action(draft: IntentDraft) -> str:
    """The registered action the words fit, when the model said nothing fits; else ""."""
    if draft.kind != "none" or draft.question:
        return ""
    names = _registered()
    if draft.fits in names:
        return draft.fits
    chosen = [name for name in dict.fromkeys(draft.choose) if name in names]
    # One choice is no choice: the words fit that action.
    return chosen[0] if len(chosen) == 1 else ""


def fitted(draft: IntentDraft) -> IntentDraft:
    """The draft as a plan (or a read) of the action the words fit; unchanged otherwise."""
    action = fitting_action(draft)
    if not action:
        return draft
    # Values the model gave for that action are kept; whatever is missing is asked.
    step = next(
        (item for item in draft.steps if item.action == action),
        DraftStep(id="s1", action=action),
    )
    kind = "answer" if action in PARAMETER_MODELS else "plan"
    return draft.model_copy(
        update={"kind": kind, "steps": [step], "fits": "", "choose": [], "related": []}
    )
