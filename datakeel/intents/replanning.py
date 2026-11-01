# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Defer later state-dependent work instead of guessing the state an earlier step will leave."""

from collections.abc import Callable

from pydantic import JsonValue

from datakeel.core.errors import NotFoundError, ValidationError
from datakeel.core.intent_models import Clarification, IntentResult
from datakeel.intents.catalog import EntityCatalog
from datakeel.intents.drafts import DraftStep, IntentDraft
from datakeel.intents.fill import FillState, fill_steps
from datakeel.intents.partial import without
from datakeel.storage.database import Database
from datakeel.storage.production_queries import project_for_params

# These actions read or change task holding, task state, workflow tier or dispatch strategy.
STATE_WORK = frozenset(
    {
        "accept_package",
        "assign_tasks",
        "claim_task",
        "configure_project",
        "finalize_project",
        "heartbeat",
        "import_predictions",
        "release_task",
        "reopen_task",
        "review_task",
        "revoke_assignment",
        "run_prelabel",
        "save_revision",
        "split_packages",
        "submit_task",
        "upgrade_project",
    }
)


def _concrete(step: DraftStep) -> dict[str, JsonValue]:
    return {key: value for key, value in step.params.items() if not isinstance(value, dict)}


def _project_id(db: Database, step: DraftStep) -> str | None:
    try:
        with db.session() as session:
            return project_for_params(session, _concrete(step))
    except (NotFoundError, ValidationError):
        return None


def replanning_barrier(db: Database, steps: list[DraftStep], language: str) -> dict[str, str]:
    """Return a deferred suffix once a later step depends on earlier task/config state.

    The first safe prefix keeps the ordinary current-database checks. Deferred steps stay in
    the draft's skipped notes, not in the executable chain, and can be planned again later.
    """
    projects = [_project_id(db, step) for step in steps]
    for index, step in enumerate(steps[1:], start=1):
        if step.action not in STATE_WORK:
            continue
        dependent = any(
            earlier.action in STATE_WORK
            and (
                projects[previous] is None
                or projects[index] is None
                or projects[previous] == projects[index]
            )
            for previous, earlier in enumerate(steps[:index])
        )
        if dependent:
            reason = "上一步完成后再规划" if language == "zh" else "deferred for replanning"
            return {later.id: reason for later in steps[index:]}
    return {}


def ready_steps(
    db: Database,
    draft: IntentDraft,
    state: FillState,
    catalog: EntityCatalog,
    text: str,
    clarify: Callable[[IntentDraft, Clarification, str], IntentResult],
) -> tuple[list[DraftStep], dict[str, dict[str, int]] | None] | IntentResult | IntentDraft:
    """Fill a draft, then keep only steps safe to check against the current database."""
    filled = fill_steps(db, draft.steps, state, catalog)
    if filled.clarification is not None:
        return clarify(draft, filled.clarification, text)
    if filled.empty_selection is not None:
        reasons = {str(filled.empty_step): filled.empty_selection}
        empty = IntentResult(kind="answer", text=filled.empty_selection, request=text)
        return (without(draft, reasons) if len(draft.steps) > 1 else None) or empty
    deferred = replanning_barrier(db, filled.steps, draft.language)
    if deferred and (narrowed := without(draft, deferred)) is not None:
        return narrowed
    return filled.steps, filled.excluded
