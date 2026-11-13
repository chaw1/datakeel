# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Replan failed steps or continue state-dependent deferred steps against the live database."""

from pydantic import JsonValue

from datakeel.core.errors import ConflictError, ValidationError
from datakeel.core.intent_models import ActionChain, DraftStep, IntentResult, PageContext
from datakeel.intents.catalog import FIELD_KINDS, build_catalog
from datakeel.intents.drafts import IntentDraft
from datakeel.intents.planner import CONTAINER_OUTPUTS, conversation_focus
from datakeel.intents.public_text import public_result
from datakeel.intents.resolve import Resolver, checked_drafts, page_state
from datakeel.intents.wording import plan_text
from datakeel.ontology.tool_models import ToolCallContext
from datakeel.storage.database import Database
from datakeel.storage.intent_chains import claim_chain, get_chain, save_chain

_CONTEXT_FIELDS = (
    "dataset_id",
    "version_id",
    "project_id",
    "package_id",
    "task_id",
    "label_set_id",
)


def _nth_item(found: JsonValue, position: JsonValue, reference: str) -> JsonValue:
    if position is None:
        return found
    if (
        not isinstance(found, list)
        or not isinstance(position, int)
        or not 0 < position <= len(found)
    ):
        message = f"{reference} has no item {position}"
        raise ValidationError(message)
    return found[position - 1]


def _substitute_done_refs(
    value: JsonValue, done_outputs: dict[str, dict[str, JsonValue]]
) -> JsonValue:
    """Resolve ``$ref`` values pointing to already-succeeded steps while keeping later refs."""
    if isinstance(value, dict) and "$ref" in value:
        reference = str(value["$ref"])
        step_id, _, output = reference.partition(".")
        if step_id not in done_outputs:
            return value
        if output not in done_outputs[step_id]:
            message = f"{reference} is not available from an executed earlier step"
            raise ValidationError(message)
        return _nth_item(done_outputs[step_id][output], value.get("$nth"), reference)
    if isinstance(value, dict):
        return {key: _substitute_done_refs(item, done_outputs) for key, item in value.items()}
    if isinstance(value, list):
        return [_substitute_done_refs(item, done_outputs) for item in value]
    return value


def _chain_focus(db: Database, chain: ActionChain) -> dict[str, str]:
    """Combine conversation focus with parameters and receipt outputs from this chain."""
    focus = conversation_focus(db, chain.conversation_id)
    keys = {*CONTAINER_OUTPUTS, *FIELD_KINDS, "task_ids"}
    for step in chain.steps:
        for source in (step.params, step.outputs, *step.items):
            for key in keys:
                value = source.get(key)
                listed = value if isinstance(value, list) else [value]
                named = [item for item in listed if isinstance(item, str)]
                if named:
                    focus[key] = ",".join(named)
    if "task_id" in focus:
        focus.setdefault("task_ids", focus["task_id"])
    return focus


def _merged_context(saved: PageContext, live: PageContext | None) -> PageContext:
    """Prefer live page fields when present, falling back to the original planned context."""
    if live is None:
        return saved
    updates: dict[str, object] = {
        field: getattr(live, field) or getattr(saved, field) for field in _CONTEXT_FIELDS
    }
    if live.selected_ids:
        updates["selected_kind"] = live.selected_kind
        updates["selected_ids"] = live.selected_ids
    else:
        updates["selected_kind"] = saved.selected_kind
        updates["selected_ids"] = saved.selected_ids
    return saved.model_copy(update=updates)


def _remaining_drafts(chain: ActionChain) -> list[DraftStep]:
    """Return unexecuted drafts from a failed chain, or deferred drafts from a completed one."""
    if chain.status == "failed":
        by_id = {step.id: step for step in chain.draft_steps}
        remaining = [
            by_id.get(step.id) or checked_drafts([step])[0]
            for step in chain.steps
            if step.status != "succeeded"
        ]
        return [*remaining, *chain.deferred_steps]
    if chain.status == "succeeded" and chain.deferred_steps:
        return list(chain.deferred_steps)
    message = "Action chain has no failed or deferred steps to replan"
    raise ConflictError(message)


def _existing_replan(db: Database, next_chain_id: str, actor: str) -> IntentResult:
    existing = get_chain(db, next_chain_id, actor=actor)
    approvals = sum(step.estimate.requires_approval for step in existing.steps)
    result = IntentResult(
        kind="plan",
        text=plan_text(len(existing.steps), approvals, existing.language),
        parser=existing.parser,
        request=existing.text,
        chain=existing,
    )
    return public_result(result, existing.language, build_catalog(db, existing.context.project_id))


def replan_chain(
    db: Database, chain_id: str, actor: str, *, context: PageContext | None = None
) -> IntentResult:
    """Replan failed steps or plan deferred steps against the live database without running."""
    chain = claim_chain(db, chain_id, actor)
    try:
        if chain.next_chain_id is not None:
            return _existing_replan(db, chain.next_chain_id, actor)
        draft_steps = _remaining_drafts(chain)
        done_outputs = {
            step.id: dict(step.outputs) for step in chain.steps if step.status == "succeeded"
        }
        substituted = [
            step.model_copy(
                update={
                    "params": {
                        key: _substitute_done_refs(val, done_outputs)
                        for key, val in step.params.items()
                    }
                }
            )
            for step in draft_steps
        ]
        effective = _merged_context(chain.context, context)
        catalog = build_catalog(db, effective.project_id)
        focus = _chain_focus(db, chain)
        state = page_state(effective, focus, actor, chain.language, chain.text)
        tool = ToolCallContext(actor=actor, session_id=chain.conversation_id)
        draft = IntentDraft(kind="plan", steps=substituted, language=chain.language)
        result = Resolver(db, catalog, state, tool).plan(
            draft, chain.text, chain.conversation_id, (chain.parser, chain.model)
        )
        checked = public_result(result, chain.language, catalog)
        if checked.chain is not None:
            chain = chain.model_copy(update={"next_chain_id": checked.chain.id})
        return checked
    finally:
        chain = save_chain(db, chain, release=True)
