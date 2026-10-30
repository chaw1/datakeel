# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""One-sentence entry: rules first, then one bounded model call, then strict checking.

The planner only proposes. It never prepares, approves or executes an action; a chain is
stored for a person to confirm in the Web UI or CLI. Read-only questions are answered at
once through the audited tool boundary with the person's own access.
"""

from collections.abc import Callable

from pydantic import Field, JsonValue
from pydantic import ValidationError as ModelValidationError

from datakeel.core.agent_models import ModelRequest, ModelResponse
from datakeel.core.errors import DatakeelError
from datakeel.core.intent_models import Clarification, IntentResult, PageContext, ParserKind
from datakeel.core.models import BoundaryModel
from datakeel.intents.catalog import EntityCatalog, build_catalog
from datakeel.intents.drafts import DraftStep, IntentDraft, language_of
from datakeel.intents.fill import FillState, known_fields
from datakeel.intents.model_parse import (
    PlannerScene,
    parse_response,
    planner_request,
    repair_request,
)
from datakeel.intents.outcomes import PlannerFailure, call_model, failed, no_fit
from datakeel.intents.recipes import match_recipe, recipe_covers
from datakeel.intents.resolve import Resolver, page_state
from datakeel.intents.rules import full_registry, is_question, rank
from datakeel.intents.verify import draft_problems
from datakeel.ontology.functions import PARAMETER_MODELS
from datakeel.ontology.tool_models import ToolCallContext
from datakeel.storage.database import Database
from datakeel.storage.identity_store import get_bindings
from datakeel.storage.intent_chains import list_chains

Complete = Callable[[ModelRequest], ModelResponse]
UNREADABLE = (DatakeelError, ModelValidationError, ValueError)
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


def _roles(db: Database, actor: str) -> list[str]:
    """The speaker's roles, so the model picks the verb's action for this person."""
    return sorted({binding.role_id for binding in get_bindings(db, actor)})


def _parsed(complete: Complete, request: ModelRequest, language: str) -> tuple[IntentDraft, str]:
    """Ask, and ask once more for an unreadable answer; a second failure is a failure."""
    response = call_model(complete, request)
    try:
        return parse_response(response.content, language), response.content
    except UNREADABLE:
        response = call_model(complete, repair_request(request, response.content))
    try:
        return parse_response(response.content, language), response.content
    except UNREADABLE as error:
        reason = "unreadable"
        raise PlannerFailure(reason) from error


def _model_draft(
    db: Database,
    turn: PlannerTurn,
    catalog: EntityCatalog,
    complete: Complete,
    access: ModelAccess,
) -> IntentDraft:
    """One bounded model call, repaired at most once per kind of problem; errors surface."""
    pending = turn.pending
    scene = PlannerScene(
        context=turn.context,
        focus=turn.focus,
        open_request=pending.request if pending else "",
        open_question=pending.text if pending else "",
        speaker=turn.actor,
        roles=_roles(db, turn.actor),
    )
    words = f"{pending.request} {turn.text}" if pending else turn.text
    request = planner_request(access.model, turn.text, rank(words, full_registry()), catalog, scene)
    language = language_of(turn.text)
    draft, content = _parsed(complete, request, language)
    draft, content = _repaired(turn, draft, catalog, complete, (request, content))
    state = page_state(turn.context, turn.focus, turn.actor, draft.language, words)
    problems = draft_problems(db, draft, state, catalog)
    if not problems:
        return draft
    # One repair round for broken rules; whatever is still broken becomes a question.
    hints = [problem.hint for problem in problems]
    try:
        fixed = parse_response(
            call_model(complete, repair_request(request, content, problems=hints)).content,
            draft.language,
        )
    except UNREADABLE:
        fixed = draft
    left = draft_problems(db, fixed, state, catalog)
    if not left:
        return fixed
    return fixed.model_copy(update={"question": left[0].question(draft.language)})


def _unknown(turn: PlannerTurn, draft: IntentDraft, catalog: EntityCatalog) -> dict[str, list[str]]:
    state = FillState(context=turn.context, focus=turn.focus, actor=turn.actor)
    found: dict[str, list[str]] = {}
    for step in draft.steps:
        _, unknown = known_fields(step, state, catalog)
        if unknown:
            found[step.action] = list(unknown)
    return found


def _repaired(
    turn: PlannerTurn,
    draft: IntentDraft,
    catalog: EntityCatalog,
    complete: Complete,
    first: tuple[ModelRequest, str],
) -> tuple[IntentDraft, str]:
    """One repair round for parameter names the action does not take.

    Unknown names are never dropped silently: the model gets one chance to use the schema's
    names; whatever is still unknown afterwards becomes a question to the person.
    """
    unknown = _unknown(turn, draft, catalog)
    if not unknown:
        return draft, first[1]
    response = call_model(complete, repair_request(first[0], first[1], unknown))
    try:
        repaired = parse_response(response.content, draft.language)
    except UNREADABLE:
        return draft, first[1]
    if repaired.steps or repaired.kind == "none":
        return repaired, response.content
    return draft, first[1]


def _draft(
    db: Database,
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
    # With a model available, a recipe only answers when it uses everything that was said.
    if recipe is not None and (not model or recipe_covers(turn.text)):
        return recipe, "rules", turn.text
    if model and complete is not None:
        return _model_draft(db, turn, catalog, complete, access), "model", turn.text
    return (_read_rule(turn.text) if access.read_rules else None), "rules", turn.text


def _no_plan(draft: IntentDraft | None, turn: PlannerTurn, *, asked: bool) -> IntentResult | None:
    """A question the checks left open, a related-actions question, or unsupported."""
    if draft is not None and draft.question:
        clarification = Clarification(question=draft.question)
        return IntentResult(
            kind="clarify", text=draft.question, request=turn.text, clarification=clarification
        )
    if not asked:
        return None
    # A model was asked: every sentence ends with an answer, never in silence.
    language = draft.language if draft is not None else language_of(turn.text)
    return no_fit(draft, turn.text, language)


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
    try:
        draft, parser, request = _draft(db, turn, catalog, complete, granted)
    except PlannerFailure as failure:
        return failed(turn.text, failure.reason, language_of(turn.text))
    if draft is None or draft.question or draft.kind == "none" or not draft.steps:
        return _no_plan(draft, turn, asked=granted.allowed and complete is not None)
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
