# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""One step per thing asked, or a reason why not: a half plan says what became of the rest.

A part the speaker may not do, or that nothing registered does, is taken out of the plan
when the other parts stand on their own (no later step uses its output). The answer and the
card then say 「另外「…」没有做: <reason>」. A part the model itself could not plan comes back
in the draft's ``skipped`` list and is reported the same way.
"""

from datakeel.actions.registry import POLICIES
from datakeel.core.intent_models import IntentResult
from datakeel.intents.catalog import EntityCatalog
from datakeel.intents.drafts import DraftStep, IntentDraft, SkippedPart
from datakeel.intents.fill import FillState
from datakeel.intents.scope_words import scope_words
from datakeel.intents.validate import REFERENCE, overreach
from datakeel.intents.wording import action_title
from datakeel.ontology.functions import PARAMETER_MODELS
from datakeel.storage.database import Database

NO_ACTION = ("平台上没有能做这件事的操作", "nothing on the platform does this")


def _no_permission(scope: str, language: str) -> str:
    named = scope_words([scope], language)
    if language == "zh":
        return f"你没有这个权限 (缺少{named}权限)"
    return f"you do not have the permission for it (it needs {named})"


def _used_later(step: DraftStep, steps: list[DraftStep]) -> bool:
    """Whether any other step takes this step's output."""
    for other in steps:
        for value in other.params.values():
            reference = value.get("$ref") if isinstance(value, dict) else None
            match = REFERENCE.match(reference) if isinstance(reference, str) else None
            if match is not None and match.group("step") == step.id:
                return True
    return False


def _reason(
    db: Database, step: DraftStep, state: FillState, catalog: EntityCatalog, language: str
) -> str | None:
    """Why this step cannot be planned for this speaker, or None when it can."""
    if step.action not in POLICIES and step.action not in PARAMETER_MODELS:
        return NO_ACTION[0] if language == "zh" else NO_ACTION[1]
    refused = overreach(db, [step], state, catalog)
    return _no_permission(refused[1][0], language) if refused is not None else None


def set_aside(
    db: Database, draft: IntentDraft, state: FillState, catalog: EntityCatalog
) -> IntentDraft:
    """Move unplannable parts into ``skipped`` while the others still make a plan."""
    if len(draft.steps) < 2:  # noqa: PLR2004
        return draft
    reasons = {step.id: _reason(db, step, state, catalog, draft.language) for step in draft.steps}
    dropped = [step for step in draft.steps if reasons[step.id] is not None]
    kept = [step for step in draft.steps if reasons[step.id] is None]
    if not dropped or not kept or any(_used_later(step, kept) for step in dropped):
        return draft
    return without(draft, {step.id: str(reasons[step.id]) for step in dropped}) or draft


def without(draft: IntentDraft, reasons: dict[str, str]) -> IntentDraft | None:
    """The draft without these steps, each reported with its reason; None if nothing stands.

    A step whose output a remaining step uses cannot be taken out.
    """
    kept = [step for step in draft.steps if step.id not in reasons]
    dropped = [step for step in draft.steps if step.id in reasons]
    if not kept or any(_used_later(step, kept) for step in dropped):
        return None
    parts = [
        SkippedPart(
            said=action_title(step.action, draft.language) if step.action in POLICIES else "",
            reason=reasons[step.id],
            source="checks",
        )
        for step in dropped
    ]
    return draft.model_copy(update={"steps": kept, "skipped": [*draft.skipped, *parts]})


def skipped_lines(parts: list[SkippedPart], text: str, language: str) -> list[str]:
    """One sentence per part not done; a model's quote is used only if the person said it."""
    lines: list[str] = []
    for part in parts:
        said = part.said.strip()
        quoted = said if said and (said in text or said in _titles(language)) else ""
        reason = part.reason.strip().rstrip("。.") if part.source == "checks" else ""
        reason = reason or (NO_ACTION[0] if language == "zh" else NO_ACTION[1])
        if language == "zh":
            subject = f"「{quoted}」" if quoted else "句子里的另一部分"
            lines.append(f"另外{subject}没有做: {reason}。")
        else:
            subject = f'"{quoted}"' if quoted else "the other part of the request"
            lines.append(f"Also, {subject} was not done: {reason}.")
    return lines


def _titles(language: str) -> set[str]:
    return {action_title(action, language) for action in POLICIES}


def with_skipped(result: IntentResult, parts: list[SkippedPart], language: str) -> IntentResult:
    """Append what became of every part not planned to the answer text."""
    lines = skipped_lines(parts, result.request, language)
    if not lines:
        return result
    joined = (" " if language == "en" else "").join(lines)
    return result.model_copy(update={"text": f"{result.text} {joined}".strip()})
