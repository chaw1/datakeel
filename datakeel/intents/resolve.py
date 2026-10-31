# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Turn an unchecked draft into a chain, a direct answer, a question or a refusal."""

import os

from pydantic import JsonValue
from pydantic import ValidationError as ModelValidationError

from datakeel.actions.registry import POLICIES
from datakeel.core.intent_models import (
    ActionChain,
    ChainStep,
    Clarification,
    IntentResult,
    PageContext,
    ParserKind,
    StepDetail,
)
from datakeel.intents.answers import run_read
from datakeel.intents.catalog import EntityCatalog
from datakeel.intents.drafts import DraftStep, IntentDraft
from datakeel.intents.duplicates import duplicate_question, taken
from datakeel.intents.exclusions import excluded_text
from datakeel.intents.fill import FillState, fill_defaults, fill_steps, known_fields
from datakeel.intents.fill_state import CONTAINER_KINDS, named_in_words
from datakeel.intents.impossible import idle_reason, impossible
from datakeel.intents.outcomes import unsupported
from datakeel.intents.partial import set_aside, skipped_lines, with_skipped, without
from datakeel.intents.public_text import allowed_words, public_notes
from datakeel.intents.read_scope import (
    assumed_note,
    missing_choices,
    one_task,
    own_projects,
    production_read,
    scope_question,
    task_argument,
    unfiltered_note,
)
from datakeel.intents.validate import bad_value, check_step, overreach, required_fields
from datakeel.intents.verify import unchanged
from datakeel.intents.wording import (
    already_so,
    broken_plan,
    invalid_question,
    plan_text,
    refusal,
)
from datakeel.label_drafts.model import PROFILES
from datakeel.ontology.functions import PARAMETER_MODELS
from datakeel.ontology.models import ObjectSet
from datakeel.ontology.tool_models import ToolCallContext
from datakeel.storage.database import Database
from datakeel.storage.intent_chains import save_chain
from datakeel.storage.label_drafts import planned_draft_cost
from datakeel.storage.object_queries import evaluate

DRAFT_SAMPLES = 8
ANNOTATION_WORDS = ("已有标注", "现有标注", "标注过", "existing annotation", "annotated")


class Resolver:
    """Check one draft for one person on one page."""

    def __init__(
        self, db: Database, catalog: EntityCatalog, state: FillState, tool: ToolCallContext
    ) -> None:
        """Bind the catalog snapshot, page context and audited tool identity."""
        self.db, self.catalog, self.state, self.tool = db, catalog, state, tool

    def _clarify(self, draft: IntentDraft, clarification: Clarification, text: str) -> IntentResult:
        return IntentResult(
            kind="clarify",
            text=clarification.question,
            request=text,
            clarification=clarification,
            draft=draft.model_dump(mode="json"),
        )

    def answer(self, draft: IntentDraft, step: DraftStep, text: str) -> IntentResult:
        """Run a read function directly once its required inputs are known.

        A filter the read does not take is not asked about: the answer comes without it and
        says so, rather than ending in a question about a setting.
        """
        step = production_read(self.db, step)
        model = PARAMETER_MODELS[step.action]
        required = {
            str(name)
            for name in model.model_json_schema().get("required", [])
            if isinstance(name, str)
        }
        known, unknown = task_argument(
            *known_fields(step, self.state, self.catalog), set(model.model_fields)
        )
        applied: set[str] = set()
        for field, kind in CONTAINER_KINDS.items():
            # A container the words name narrows the read even where it is optional.
            named = named_in_words(field, self.state, self.catalog)
            entry = self.catalog.get(kind, named) if named else None
            if entry is not None and field in model.model_fields and field not in known:
                known[field] = entry.id
                applied.update({entry.label, *entry.names})
        unfiltered = unfiltered_note(unknown, text, draft.language, frozenset(applied))
        bounded = step.model_copy(update={"params": known})
        filled = fill_steps(self.db, [bounded], self.state, self.catalog)
        if filled.clarification is not None:
            return self._clarify(draft, filled.clarification, text)
        if not filled.steps:
            # The words describe tasks that do not exist: say so instead of reading nothing.
            return IntentResult(kind="answer", text=filled.empty_selection or "", request=text)
        single = one_task(filled.steps[0].params, draft.language)
        if isinstance(single, Clarification):
            return self._clarify(draft, single.model_copy(update={"action": step.action}), text)
        first = filled.steps[0].model_copy(update={"params": single})
        current = fill_defaults(first, required, self.state, self.catalog)
        scoped = self._scoped(draft, first, current, required)
        if isinstance(scoped, Clarification):
            return self._clarify(draft, scoped, text)
        current, note = scoped
        try:
            model.model_validate(current.params)
        except ModelValidationError as error:
            problem = "|".join(bad_value(item, step.action) for item in error.errors())
            question = invalid_question(problem, draft.language)
            asked = Clarification(question=question, action=step.action)
            return self._clarify(draft, asked, text)
        answer, sentence = run_read(self.db, step.action, current.params, self.tool, draft.language)
        return IntentResult(
            kind="answer", text=note + sentence + unfiltered, request=text, answer=answer
        )

    def _scoped(
        self, draft: IntentDraft, before: DraftStep, current: DraftStep, required: set[str]
    ) -> tuple[DraftStep, str] | Clarification:
        """A read's missing project: the speaker's only one (said aloud), else a choice."""
        missing = sorted(required - set(current.params))
        note = self._assumed(before, current, draft.language)
        if missing == ["project_id"]:
            own = own_projects(self.db, self.state.actor, self.catalog)
            if len(own) != 1:
                return scope_question(current.action, missing, draft.language, own)
            params = {**current.params, "project_id": own[0].id}
            return current.model_copy(update={"params": params}), assumed_note(
                own[0], draft.language
            )
        if missing:
            choices = missing_choices(missing[0], self.catalog) if len(missing) == 1 else []
            return scope_question(current.action, missing, draft.language, choices)
        return current, note

    def _assumed(self, before: DraftStep, after: DraftStep, language: str) -> str:
        """The only project, filled although neither page nor words gave one, is said."""
        project = after.params.get("project_id")
        given = "project_id" in before.params or self.state.context.project_id
        named = named_in_words("project_id", self.state, self.catalog)
        entry = self.catalog.get("project", project) if isinstance(project, str) else None
        if entry is None or given or named or self.state.focus.get("project_id"):
            return ""
        return assumed_note(entry, language)

    def _draft_sources(self, step: DraftStep, text: str) -> DraftStep:
        params: dict[str, JsonValue] = dict(step.params)
        context = self.state.context
        topic = str(params.get("topic") or params.get("name") or "")
        dataset = params.get("dataset_id") or context.dataset_id
        if dataset and "sample_ids" not in params:
            files = context.selected_kind in {None, "file"}
            selected: list[str] = list(context.selected_ids) if files else []
            versions = [context.version_id] if context.version_id else []
            if not selected:
                manifest = evaluate(
                    self.db,
                    ObjectSet(dataset_id=str(dataset), version_ids=versions, limit=DRAFT_SAMPLES),
                )
                selected = [item.asset_ref.asset_id for item in manifest.objects]
            samples: list[JsonValue] = list(selected[:DRAFT_SAMPLES])
            params["dataset_id"] = dataset
            params["sample_ids"] = samples
            if context.version_id:
                params.setdefault("version_id", context.version_id)
        if "standard_codes" not in params and topic:
            found = self.catalog.mentioned("standard", text) + self.catalog.mentioned(
                "code_list", text
            )
            found = (
                found
                or self.catalog.match("standard", topic)
                or self.catalog.match("code_list", topic)
            )
            if found:
                params["standard_codes"] = [entry.id for entry in found[:5]]
        if context.label_set_id and "label_set_ids" not in params:
            params["label_set_ids"] = [context.label_set_id]
        if dataset and any(word in text.casefold() for word in ANNOTATION_WORDS):
            params.setdefault("annotation_dataset_ids", [dataset])
        chosen = params.get("sample_ids")
        if "profile" not in params:
            # A configured model translates names and writes rules; images need the vision one.
            wanted = ("cloud-vision", "cloud-text") if chosen else ("cloud-text",)
            params["profile"] = next(
                (name for name in wanted if os.environ.get(PROFILES[name].api_key_env)), "offline"
            )
        if params["profile"] != "offline" and "max_cost_usd" not in params:
            # Execution checks the budget against the same sources counted here.
            params["max_cost_usd"] = max(planned_draft_cost(self.db, params), 0.001)
        return step.model_copy(update={"params": params})

    def _checked(
        self,
        draft: IntentDraft,
        steps: list[DraftStep],
        text: str,
        excluded: dict[str, dict[str, int]] | None = None,
    ) -> list[ChainStep] | IntentResult:
        checked: list[ChainStep] = []
        left_out = excluded or {}
        for position, step in enumerate(steps):
            current = self._draft_sources(step, text) if step.action == "draft_label_set" else step
            required = required_fields(current.action)
            current = fill_defaults(current, required, self.state, self.catalog)
            result = check_step(self.db, current, self.state, self.catalog, checked)
            if result.clarification is not None:
                rest = [*checked_drafts(checked), current, *steps[position + 1 :]]
                kept = draft.model_copy(update={"steps": rest})
                return self._clarify(kept, result.clarification, text)
            if result.missing_scopes:
                return IntentResult(
                    kind="refuse",
                    text=refusal(current.action, result.missing_scopes, draft.language),
                    request=text,
                    missing_scopes=result.missing_scopes,
                )
            if result.step is None and current.action not in POLICIES:
                # An action the registry does not have: nothing registered does this.
                return unsupported(text, draft.language)
            if result.step is None:
                # The internal reason stays out of the answer; the person hears a plain one.
                return IntentResult(kind="clarify", text=broken_plan(draft.language), request=text)
            checked.append(_with_exclusions(result.step, left_out.get(step.id), draft.language))
        return checked

    def _notes(self, draft: IntentDraft, text: str) -> list[str]:
        allowed = allowed_words(self.catalog, text)
        return public_notes(draft.notes, draft.language, self.catalog, allowed)

    def plan(
        self,
        draft: IntentDraft,
        text: str,
        conversation_id: str | None,
        origin: tuple[ParserKind, str | None] = ("rules", None),
    ) -> IntentResult:
        """Fill, check and persist a chain; nothing is prepared or executed here.

        Permission comes first: a write the speaker may not perform is refused before any
        question about its parameters is asked.
        """
        result: IntentResult | IntentDraft = set_aside(self.db, draft, self.state, self.catalog)
        # A narrower draft comes back when a part was set aside; each round drops at least one.
        while isinstance(result, IntentDraft):
            draft = result
            result = self._plan(draft, text, conversation_id, origin)
        return with_skipped(result, draft.skipped, draft.language)

    def _stopped(self, draft: IntentDraft, text: str) -> IntentResult | None:
        """A refusal, or a new name that is taken: both come before any other question."""
        refused = overreach(self.db, draft.steps, self.state, self.catalog)
        if refused is not None:
            action, scopes = refused
            return IntentResult(
                kind="refuse",
                text=refusal(action, scopes, draft.language),
                request=text,
                missing_scopes=scopes,
            )
        for step in draft.steps:
            found = taken(self.db, step, self.catalog)
            if found is not None:
                asked = duplicate_question(step, found, draft.language)
                return self._clarify(draft, asked, text)
        return None

    def _settled(
        self, draft: IntentDraft, checked: list[ChainStep], text: str
    ) -> IntentResult | IntentDraft | None:
        """Parts execution must refuse, or that change nothing, never reach a card.

        With other parts standing they are set aside and said; alone they are answered.
        """
        refused: dict[str, str] = {}
        idle: dict[str, str] = {}
        for step in checked:
            reason = impossible(self.db, step, draft.language)
            if reason is not None:
                refused[step.id] = reason
            elif unchanged(self.db, step):
                idle[step.id] = idle_reason(step.action, draft.language)
        reasons = {**idle, **refused}
        narrowed = without(draft, reasons) if 0 < len(reasons) < len(checked) else None
        if narrowed is not None:
            return narrowed
        if refused:
            ending = "。" if draft.language == "zh" else "."
            sentence = next(iter(refused.values()))
            spoken = sentence[:1].upper() + sentence[1:] + ending
            return IntentResult(kind="answer", text=spoken, request=text)
        if checked and len(idle) == len(checked):
            return IntentResult(kind="answer", text=already_so(draft.language), request=text)
        return None

    def _plan(
        self,
        draft: IntentDraft,
        text: str,
        conversation_id: str | None,
        origin: tuple[ParserKind, str | None],
    ) -> IntentResult | IntentDraft:
        stopped = self._stopped(draft, text)
        if stopped is not None:
            return stopped
        filled = fill_steps(self.db, draft.steps, self.state, self.catalog)
        if filled.clarification is not None:
            return self._clarify(draft, filled.clarification, text)
        if filled.empty_selection is not None:
            # The part that matched nothing is set aside when the rest stands alone.
            reasons = {str(filled.empty_step): filled.empty_selection}
            empty = IntentResult(kind="answer", text=filled.empty_selection, request=text)
            return (without(draft, reasons) if len(draft.steps) > 1 else None) or empty
        checked = self._checked(draft, filled.steps, text, filled.excluded)
        if isinstance(checked, IntentResult):
            return checked
        settled = self._settled(draft, checked, text)
        if settled is not None:
            return settled
        chain = save_chain(
            self.db,
            ActionChain(
                conversation_id=conversation_id,
                actor=self.state.actor,
                text=text,
                language=draft.language,
                steps=checked,
                # Only rule notes are kept: they are generated from the parameters. A model's
                # own description could claim a change the parameters do not make.
                notes=[
                    *(self._notes(draft, text) if origin[0] == "rules" else []),
                    *skipped_lines(draft.skipped, text, draft.language),
                ],
                parser=origin[0],
                model=origin[1],
            ),
        )
        approvals = sum(step.estimate.requires_approval for step in checked)
        return IntentResult(
            kind="plan",
            text=plan_text(len(checked), approvals, draft.language),
            request=text,
            chain=chain,
        )


def _with_exclusions(step: ChainStep, excluded: dict[str, int] | None, language: str) -> ChainStep:
    """Say on the card how many described tasks protection left out, and why."""
    if not excluded:
        return step
    label = "已排除" if language == "zh" else "Left out"
    detail = StepDetail(label=label, value=excluded_text(excluded, language).strip(), tone="impact")
    return step.model_copy(update={"details": [*step.details, detail]})


def checked_drafts(steps: list[ChainStep]) -> list[DraftStep]:
    """Return checked steps to draft form so a follow-up answer can resume from them."""
    drafts: list[DraftStep] = []
    for step in steps:
        params = dict(step.params)
        for key in step.items[0] if step.items else {}:
            params[key] = {"$each": [item.get(key) for item in step.items]}
        drafts.append(DraftStep(id=step.id, action=step.action, params=params))
    return drafts


def page_state(
    context: PageContext | None,
    focus: dict[str, str],
    actor: str,
    language: str,
    text: str = "",
) -> FillState:
    """Bundle the page, the previous turn, the person and their words for filling."""
    return FillState(
        context=context or PageContext(), focus=focus, actor=actor, language=language, text=text
    )
