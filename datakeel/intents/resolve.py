# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Turn an unchecked draft into a chain, a direct answer, a question or a refusal."""

import os

from pydantic import JsonValue
from pydantic import ValidationError as ModelValidationError

from datakeel.core.intent_models import (
    ActionChain,
    ChainStep,
    Clarification,
    IntentResult,
    PageContext,
    ParserKind,
)
from datakeel.intents.answers import run_read
from datakeel.intents.catalog import EntityCatalog
from datakeel.intents.drafts import DraftStep, IntentDraft
from datakeel.intents.fill import FillState, fill_defaults, fill_steps
from datakeel.intents.validate import check_step, overreach, required_fields
from datakeel.intents.wording import field_label, plan_text, refusal
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
        """Run a read function directly once its required inputs are known."""
        model = PARAMETER_MODELS[step.action]
        required = {
            str(name)
            for name in model.model_json_schema().get("required", [])
            if isinstance(name, str)
        }
        filled = fill_steps(self.db, [step], self.state, self.catalog)
        if filled.clarification is not None:
            return self._clarify(draft, filled.clarification, text)
        current = fill_defaults(filled.steps[0], required, self.state, self.catalog)
        missing = sorted(required - set(current.params))
        if missing:
            names = "、".join(field_label(item, draft.language) for item in missing)
            question = (
                f"要回答这个问题, 还缺: {names}。"
                if draft.language == "zh"
                else f"I need: {names}."
            )
            clarification = Clarification(question=question, action=step.action, fields=missing)
            return self._clarify(draft, clarification, text)
        try:
            model.model_validate(current.params)
        except ModelValidationError as error:
            return self._clarify(
                draft,
                Clarification(question=str(error.errors()[0]["msg"]), action=step.action),
                text,
            )
        answer, sentence = run_read(self.db, step.action, current.params, self.tool, draft.language)
        return IntentResult(kind="answer", text=sentence, request=text, answer=answer)

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
        self, draft: IntentDraft, steps: list[DraftStep], text: str
    ) -> list[ChainStep] | IntentResult:
        checked: list[ChainStep] = []
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
            if result.step is None:
                zh = draft.language == "zh"
                prefix = "这个计划不能执行: " if zh else "This plan cannot run: "
                return IntentResult(kind="refuse", text=prefix + (result.error or ""), request=text)
            checked.append(result.step)
        return checked

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
        refused = overreach(self.db, draft.steps, self.state, self.catalog)
        if refused is not None:
            action, scopes = refused
            return IntentResult(
                kind="refuse",
                text=refusal(action, scopes, draft.language),
                request=text,
                missing_scopes=scopes,
            )
        filled = fill_steps(self.db, draft.steps, self.state, self.catalog)
        if filled.clarification is not None:
            return self._clarify(draft, filled.clarification, text)
        if filled.empty_selection is not None:
            return IntentResult(kind="answer", text=filled.empty_selection, request=text)
        checked = self._checked(draft, filled.steps, text)
        if isinstance(checked, IntentResult):
            return checked
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
                notes=draft.notes if origin[0] == "rules" else [],
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


def checked_drafts(steps: list[ChainStep]) -> list[DraftStep]:
    """Return checked steps to draft form so a follow-up answer can resume from them."""
    drafts: list[DraftStep] = []
    for step in steps:
        params = dict(step.params)
        if step.items:
            key = next(iter(step.items[0]))
            params[key] = {"$each": [item[key] for item in step.items]}
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
