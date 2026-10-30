# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Check filled steps against the registered parameter schemas, scopes and references."""

import re

from pydantic import Field, JsonValue
from pydantic import ValidationError as ModelValidationError

from datakeel.actions.parameters import PARAMETER_TYPES
from datakeel.actions.registry import POLICIES
from datakeel.core.errors import NotFoundError, ValidationError
from datakeel.core.intent_models import ChainStep, Clarification
from datakeel.core.models import BoundaryModel
from datakeel.intents.catalog import EntityCatalog
from datakeel.intents.drafts import DraftStep
from datakeel.intents.estimates import estimate_step
from datakeel.intents.fill import FillState
from datakeel.intents.wording import missing_question
from datakeel.storage.database import Database
from datakeel.storage.identity_authorization import effective_scopes
from datakeel.storage.production_queries import project_for_params

REFERENCE = re.compile(r"^(?P<step>s\d{1,2})\.(?P<output>[a-z_]+_(?:id|ids|version))$")


class StepCheck(BoundaryModel):
    """A checked chain step, a question to ask, or the scopes the person lacks."""

    step: ChainStep | None = None
    clarification: Clarification | None = None
    missing_scopes: list[str] = Field(default_factory=list[str])
    error: str | None = None


def required_fields(action: str) -> set[str]:
    """Parameters without defaults, except the generated retry identity."""
    model = PARAMETER_TYPES.get(action)
    if model is None:
        return set()
    schema = model.model_json_schema()
    required = schema.get("required", [])
    return {str(name) for name in required if isinstance(name, str)} - {"request_id"}


def _placeholder(value: JsonValue) -> JsonValue:
    if isinstance(value, dict):
        if "$ref" in value:
            output = str(value["$ref"])
            if output.endswith("_version"):
                return 1
            return ["placeholder"] if output.endswith("_ids") else "placeholder"
        if "$each" in value:
            each = value["$each"]
            return each[0] if isinstance(each, list) and each else "placeholder"
        return {key: _placeholder(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_placeholder(item) for item in value]
    return value


def _references(step: DraftStep, earlier: set[str]) -> str | None:
    for value in step.params.values():
        if isinstance(value, dict) and "$ref" in value:
            match = REFERENCE.match(str(value["$ref"]))
            if match is None or match.group("step") not in earlier:
                return f"{step.id} refers to an unknown earlier output: {value['$ref']}"
    return None


def _schema_problems(step: DraftStep) -> tuple[list[str], str | None]:
    model = PARAMETER_TYPES[step.action]
    try:
        model.model_validate({key: _placeholder(value) for key, value in step.params.items()})
    except ModelValidationError as error:
        missing = [
            str(item["loc"][0])
            for item in error.errors()
            if item["type"] == "missing" and item["loc"]
        ]
        others = [
            str(item["msg"]).removeprefix("Value error, ")
            for item in error.errors()
            if item["type"] != "missing"
        ]
        return missing, "; ".join(others) or None
    return [], None


def _granted(db: Database, step: DraftStep, actor: str) -> tuple[bool, bool]:
    """Return (granted, project_known) using the same project resolution as execution."""
    concrete: dict[str, JsonValue] = {}
    for key, value in step.params.items():
        if isinstance(value, dict) and "$each" in value:
            each = value["$each"]
            if isinstance(each, list) and each:
                concrete[key] = each[0]
        elif not (isinstance(value, dict) and "$ref" in value):
            concrete[key] = value
    scope = POLICIES[step.action][0]
    with db.session() as session:
        try:
            project = project_for_params(session, concrete)
        except (NotFoundError, ValidationError):
            project = None
        granted = effective_scopes(session, actor, project).scopes
    return "*" in granted or scope in granted, project is not None


def check_step(
    db: Database,
    step: DraftStep,
    state: FillState,
    catalog: EntityCatalog,
    previous: list[ChainStep],
) -> StepCheck:
    """Validate one step; refuse overreach before asking for anything else."""
    earlier, actor, language = {item.id for item in previous}, state.actor, state.language
    if step.action not in PARAMETER_TYPES or step.action not in POLICIES:
        return StepCheck(error=f"Unknown action: {step.action}")
    problem = _references(step, earlier)
    if problem:
        return StepCheck(error=problem)
    missing, invalid = _schema_problems(step)
    granted, project_known = _granted(db, step, actor)
    if not granted and (project_known or "project_id" not in missing):
        return StepCheck(missing_scopes=[POLICIES[step.action][0]])
    if missing:
        return StepCheck(
            clarification=Clarification(
                question=missing_question(step.action, missing, language),
                action=step.action,
                fields=missing,
            )
        )
    if invalid:
        return StepCheck(
            clarification=Clarification(question=invalid, action=step.action, fields=[])
        )
    scope = POLICIES[step.action][0]
    params = dict(step.params)
    items: list[dict[str, JsonValue]] = []
    for key, value in list(params.items()):
        if isinstance(value, dict) and "$each" in value and isinstance(value["$each"], list):
            items = [{key: item} for item in value["$each"]]
            params.pop(key)
    chain_step = ChainStep(id=step.id, action=step.action, params=params, items=items, scope=scope)
    estimate = estimate_step(db, chain_step, catalog, previous)
    return StepCheck(step=chain_step.model_copy(update={"estimate": estimate}))
