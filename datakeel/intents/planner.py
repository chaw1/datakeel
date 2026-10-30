# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""One-sentence entry: rules first, then one bounded model call, then strict checking.

The planner only proposes. It never prepares, approves or executes an action; a chain is
stored for a person to confirm in the Web UI or CLI. Read-only questions are answered at
once through the audited tool boundary with the person's own access.
"""

from collections.abc import Callable

import httpx
from pydantic import Field, JsonValue
from pydantic import ValidationError as ModelValidationError

from datakeel.core.agent_models import ModelRequest, ModelResponse
from datakeel.core.errors import DatakeelError
from datakeel.core.intent_models import IntentResult, PageContext, ParserKind
from datakeel.core.models import BoundaryModel
from datakeel.intents.catalog import EntityCatalog, build_catalog
from datakeel.intents.drafts import DraftStep, IntentDraft, language_of
from datakeel.intents.model_parse import PlannerScene, parse_response, planner_request
from datakeel.intents.recipes import match_recipe
from datakeel.intents.resolve import Resolver, page_state
from datakeel.intents.rules import full_registry, is_question, rank
from datakeel.ontology.functions import PARAMETER_MODELS
from datakeel.ontology.tool_models import ToolCallContext
from datakeel.storage.database import Database
from datakeel.storage.intent_chains import list_chains

Complete = Callable[[ModelRequest], ModelResponse]
READ_SCORE = 2.5
READ_MARGIN = 1.5
REPLY_LIMIT = 40
CONTAINER_OUTPUTS = ("dataset_id", "version_id", "project_id", "package_id", "label_set_id")


class PlannerTurn(BoundaryModel):
    """One user sentence with the page, the previous turn and any open question."""

    text: str = Field(min_length=1, max_length=80000)
    actor: str = "local"
    conversation_id: str | None = None
    context: PageContext = Field(default_factory=PageContext)
    pending: IntentResult | None = None
    focus: dict[str, str] = Field(default_factory=dict[str, str])


class ModelAccess(BoundaryModel):
    """Whether this turn may ask a model, and which one."""

    model: str = ""
    allowed: bool = False
    read_rules: bool = True


def conversation_focus(db: Database, conversation_id: str | None) -> dict[str, str]:
    """Objects the previous chain named or created, so 'it' and 'that project' resolve."""
    focus: dict[str, str] = {}
    chains = list_chains(db, conversation_id) if conversation_id else []
    for step in chains[-1].steps if chains else []:
        for source in (step.params, step.outputs):
            for key in CONTAINER_OUTPUTS:
                value = source.get(key)
                if isinstance(value, str):
                    focus[key] = value
    return focus


def _read_rule(text: str) -> IntentDraft | None:
    if not is_question(text):
        return None
    ranked = rank(text, full_registry())
    top = ranked[0] if ranked else None
    runner_up = ranked[1].score if len(ranked) > 1 else 0
    if top is None or top.kind != "function" or top.score < READ_SCORE:
        return None
    if top.score - runner_up < READ_MARGIN:
        return None
    step = DraftStep(id="s1", action=top.name)
    return IntentDraft(kind="answer", steps=[step], language=language_of(text), confident=True)


def _value(reply: str, turn: PlannerTurn) -> JsonValue:
    pending = turn.pending.clarification if turn.pending else None
    wanted = reply.strip().casefold()
    for candidate in pending.candidates if pending else []:
        if wanted in {candidate.id.casefold(), candidate.label.casefold()}:
            return candidate.id
    stripped = reply.strip()
    if stripped.isdigit():
        return int(stripped)
    try:
        return float(stripped)
    except ValueError:
        return stripped


def _with_selector(value: JsonValue, field: str, answer: JsonValue) -> JsonValue:
    selector = value.get("$tasks") if isinstance(value, dict) else None
    if isinstance(selector, dict):
        return {"$tasks": {**selector, field: answer}}
    return value


def _picked(turn: PlannerTurn) -> bool:
    pending = turn.pending.clarification if turn.pending else None
    wanted = turn.text.strip().casefold()
    return pending is not None and any(
        wanted in {item.id.casefold(), item.label.casefold()} for item in pending.candidates
    )


def merge_reply(turn: PlannerTurn, *, picked_only: bool = False) -> IntentDraft | None:
    """Fill the single value an open question asked for with the person's reply.

    With a model available only a picked candidate is merged by rules; any other reply goes
    to the model together with the open question.
    """
    pending = turn.pending
    if pending is None or pending.clarification is None or not pending.draft:
        return None
    if picked_only and not _picked(turn):
        return None
    if len(turn.text) > REPLY_LIMIT or match_recipe(turn.text) is not None:
        return None
    fields = pending.clarification.fields
    try:
        draft = IntentDraft.model_validate(pending.draft)
    except ModelValidationError:
        return None
    if len(fields) != 1:
        return None
    field, answer = fields[0], _value(turn.text, turn)
    steps: list[DraftStep] = []
    placed = False
    for step in draft.steps:
        params = dict(step.params)
        if field.startswith("$tasks."):
            name = field.removeprefix("$tasks.")
            params = {key: _with_selector(value, name, answer) for key, value in params.items()}
        elif not placed and step.action == pending.clarification.action:
            params[field] = answer
            placed = True
        steps.append(step.model_copy(update={"params": params}))
    return draft.model_copy(update={"steps": steps})


def _model_draft(
    turn: PlannerTurn, catalog: EntityCatalog, complete: Complete, access: ModelAccess
) -> IntentDraft | None:
    pending = turn.pending
    scene = PlannerScene(
        context=turn.context,
        focus=turn.focus,
        open_request=pending.request if pending else "",
        open_question=pending.text if pending else "",
    )
    words = f"{pending.request} {turn.text}" if pending else turn.text
    request = planner_request(access.model, turn.text, rank(words, full_registry()), catalog, scene)
    try:
        response = complete(request)
        return parse_response(response.content, language_of(turn.text))
    except (DatakeelError, httpx.HTTPError, ModelValidationError, ValueError):
        return None


def _draft(
    turn: PlannerTurn,
    catalog: EntityCatalog,
    complete: Complete | None,
    access: ModelAccess,
) -> tuple[IntentDraft | None, ParserKind, str]:
    """Return the request text to plan for; a merged reply keeps the original request."""
    model = access.allowed and complete is not None
    merged = merge_reply(turn, picked_only=model)
    if merged is not None and turn.pending is not None:
        return merged, turn.pending.parser, turn.pending.request
    recipe = match_recipe(turn.text)
    if recipe is not None:
        return recipe, "rules", turn.text
    if model and complete is not None:
        drafted = _model_draft(turn, catalog, complete, access)
        if drafted is not None:
            return drafted, "model", turn.text
    return (_read_rule(turn.text) if access.read_rules else None), "rules", turn.text


def plan_turn(
    db: Database,
    turn: PlannerTurn,
    *,
    complete: Complete | None = None,
    access: ModelAccess | None = None,
) -> IntentResult | None:
    """Return a checked result, or None when the free conversation should answer instead."""
    granted = access or ModelAccess()
    catalog = build_catalog(db, turn.context.project_id)
    draft, parser, request = _draft(turn, catalog, complete, granted)
    if draft is None or draft.kind == "none" or not draft.steps:
        return None
    words = f"{request} {turn.text}" if request != turn.text else turn.text
    state = page_state(turn.context, turn.focus, turn.actor, draft.language, words)
    tool = ToolCallContext(actor=turn.actor, session_id=turn.conversation_id)
    resolver = Resolver(db, catalog, state, tool)
    reads = [step for step in draft.steps if step.action in PARAMETER_MODELS]
    if draft.kind == "answer" or (len(draft.steps) == 1 and reads):
        if not reads:
            return None
        result = resolver.answer(draft, reads[0], request)
    else:
        writes = draft.model_copy(update={"steps": [s for s in draft.steps if s not in reads]})
        if not writes.steps:
            # Several reads and no write: answer the first read rather than build a chain.
            return resolver.answer(draft, reads[0], request).model_copy(update={"parser": parser})
        origin = (parser, granted.model if parser == "model" else None)
        result = resolver.plan(writes, request, turn.conversation_id, origin)
    return result.model_copy(update={"parser": parser})
