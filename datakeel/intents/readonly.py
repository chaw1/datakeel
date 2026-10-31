# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""A question about the current state is answered, never planned as the change it names.

"南区车道定稿了吗?" names finalizing, but asks whether it happened. Whatever the model
proposes, a status question whose plan would change something becomes a read of the same
object: the registered read function that takes the most specific identity the plan names.
No request words ("帮我", "能不能", "please") may be in the sentence.
"""

import re
from collections.abc import Sequence
from typing import TYPE_CHECKING

from datakeel.intents.drafts import DraftStep, IntentDraft
from datakeel.intents.rules import RankedEntry
from datakeel.ontology.functions import PARAMETER_MODELS

if TYPE_CHECKING:
    from pydantic import JsonValue

ASKED_ZH = re.compile(r"(?:吗|没|没有|呢|[?\uff1f])\s*$|是否|有没有|是不是")
DONE_ZH = re.compile(r"了|过|已经|是否|有没有|是不是|还在|还没")
ASKED_EN = re.compile(r"^\s*(?:has|have|is|are|was|were|did|does|do)\b.*\?\s*$", re.IGNORECASE)
REQUEST = re.compile(
    r"^\s*(?:请|麻烦|帮)|帮我|帮忙|能不能|可不可以|能否|可以|能帮|要不要|需不需要|我想|我要|给我|"
    r"顺便|的话|\b(?:can|could|would|will|please|if not|otherwise|possible|able to)\b",
    re.IGNORECASE,
)
# Identities from the most to the least specific, each read by the functions that take it.
IDENTITIES = ("task_id", "package_id", "asset_id", "label_set_id", "project_id", "dataset_id")


def status_question(text: str) -> bool:
    """Whether the sentence only asks how things stand ("提交了没有?", "Has it been...?")."""
    if REQUEST.search(text):
        return False
    if ASKED_EN.search(text):
        return True
    return bool(ASKED_ZH.search(text) and DONE_ZH.search(text))


def _status_read(step: DraftStep, ranked: Sequence[RankedEntry]) -> DraftStep | None:
    # The words pick among the reads that fit; with no evidence, the registry's first one.
    order = {entry.name: place for place, entry in enumerate(ranked) if entry.score > 0}
    for key in IDENTITIES:
        value = step.params.get(key) or (step.params.get("task_ids") if key == "task_id" else None)
        if value is None:
            continue
        given = {key, *step.params}
        reads = [
            name
            for name, model in PARAMETER_MODELS.items()
            if key in model.model_fields
            and all(
                field in given for field, info in model.model_fields.items() if info.is_required()
            )
        ]
        if reads:
            name = min(reads, key=lambda read: order.get(read, len(order)))
            carried: dict[str, JsonValue] = {
                field: given
                for field, given in step.params.items()
                if field in PARAMETER_MODELS[name].model_fields and field != key
            }
            return DraftStep(id=step.id, action=name, params={**carried, key: value})
    return None


def read_only(draft: IntentDraft, text: str, ranked: Sequence[RankedEntry]) -> IntentDraft:
    """A write plan for a status question becomes the read of what it names."""
    writes = [step for step in draft.steps if step.action not in PARAMETER_MODELS]
    if draft.kind != "plan" or not writes or not status_question(text):
        return draft
    reads = [read for step in writes if (read := _status_read(step, ranked)) is not None]
    kept = [step for step in draft.steps if step.action in PARAMETER_MODELS]
    if not reads and not kept:
        return draft
    return draft.model_copy(update={"kind": "answer", "steps": [*kept, *reads[:1]]})
