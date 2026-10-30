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
from datakeel.intents.catalog import FIELD_KINDS, LIST_KINDS, EntityCatalog, candidates
from datakeel.intents.describe import describe_step
from datakeel.intents.drafts import DraftStep
from datakeel.intents.estimates import estimate_step
from datakeel.intents.fill import FillState, context_value
from datakeel.intents.wording import invalid_question, missing_question, subset_question
from datakeel.ontology.functions import PARAMETER_MODELS
from datakeel.storage.database import Database
from datakeel.storage.identity_authorization import effective_scopes
from datakeel.storage.production_queries import project_for_params

REFERENCE = re.compile(r"^(?P<step>s\d{1,2})\.(?P<output>[a-z_]+_(?:id|ids|version))$")
# A sentence that describes part of a dataset; a plan for the whole dataset is then wrong.
SUBSET = re.compile(
    r"重复|那几|这几|其中|部分|选中|勾选|模糊|低质|有问题|损坏|空白|"
    r"\b(duplicat\w*|some of|a few|selected|these few|blurry|low[- ]quality|broken|corrupt\w*)\b",
    re.IGNORECASE,
)


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


def _named_fields(message: str, absent: set[str]) -> list[str]:
    """Absent parameters a validator message names, e.g. "assignment requires actor"."""
    return sorted(name for name in absent if re.search(rf"\b{re.escape(name)}\b", message))


def _schema_problems(step: DraftStep) -> tuple[list[str], str | None]:
    """Missing parameters (also those a rule requires) and any other invalid value."""
    model = PARAMETER_TYPES[step.action]
    try:
        model.model_validate({key: _placeholder(value) for key, value in step.params.items()})
    except ModelValidationError as error:
        missing = [
            str(item["loc"][0])
            for item in error.errors()
            if item["type"] == "missing" and item["loc"]
        ]
        absent = set(model.model_fields) - set(step.params) - {"request_id"}
        others: list[str] = []
        for item in error.errors():
            if item["type"] == "missing":
                continue
            message = str(item["msg"]).removeprefix("Value error, ")
            named = _named_fields(message, absent)
            missing += [name for name in named if name not in missing]
            if not named:
                others.append(message)
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


def _scope_anywhere(db: Database, actor: str, scope: str, projects: list[str]) -> bool:
    with db.session() as session:
        for project in [None, *projects]:
            granted = effective_scopes(session, actor, project).scopes
            if "*" in granted or scope in granted:
                return True
    return False


def overreach(
    db: Database, steps: list[DraftStep], state: FillState, catalog: EntityCatalog
) -> tuple[str, list[str]] | None:
    """The first write the speaker may not perform, checked before anything is asked.

    With a known project (named, on the page or from the last turn) the project's roles
    count; otherwise the speaker must hold the scope globally or in at least one project.
    """
    projects = [entry.id for entry in catalog.of("project")]
    for step in steps:
        if step.action in PARAMETER_MODELS or step.action not in POLICIES:
            continue
        scope = POLICIES[step.action][0]
        named = step.params.get("project_id")
        project = (
            named
            if isinstance(named, str) and catalog.get("project", named)
            else context_value("project_id", state, catalog)
        )
        allowed = (
            _scope_anywhere(db, state.actor, scope, [project])
            if project
            else _scope_anywhere(db, state.actor, scope, projects)
        )
        if not allowed:
            return step.action, [scope]
    return None


def _missing(
    step: DraftStep, missing: list[str], state: FillState, catalog: EntityCatalog
) -> Clarification:
    """Ask in words for what is missing; one missing object comes with up to five choices."""
    field = missing[0] if len(missing) == 1 else None
    kind = FIELD_KINDS.get(field or "") or LIST_KINDS.get(field or "")
    choices = candidates(catalog.of(kind)) if kind and kind != "task" else []
    return Clarification(
        question=missing_question(step.action, missing, state.language),
        action=step.action,
        fields=missing,
        candidates=choices,
    )


def wider_than_said(step: DraftStep, text: str) -> bool:
    """A whole-dataset selection for a sentence that names a subset is a wrong plan."""
    selection = step.params.get("selection")
    if not isinstance(selection, dict) or not SUBSET.search(text):
        return False
    narrowed = any(
        selection.get(key) not in (None, [], "")
        for key in ("filters", "assertion_filters", "quality_min", "quality_max", "split")
    )
    return not narrowed and not selection.get("has_near_duplicate_in")


def _question(
    step: DraftStep,
    missing: list[str],
    invalid: str | None,
    state: FillState,
    catalog: EntityCatalog,
) -> Clarification | None:
    if missing:
        return _missing(step, missing, state, catalog)
    if wider_than_said(step, state.text):
        question = subset_question(state.language)
        return Clarification(question=question, action=step.action, fields=["selection"])
    if invalid:
        question = invalid_question(invalid, state.language)
        return Clarification(question=question, action=step.action, fields=[])
    return None


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
    asked = _question(step, missing, invalid, state, catalog)
    if asked is not None:
        return StepCheck(clarification=asked)
    scope = POLICIES[step.action][0]
    params = dict(step.params)
    items: list[dict[str, JsonValue]] = []
    for key, value in list(params.items()):
        if isinstance(value, dict) and "$each" in value and isinstance(value["$each"], list):
            items = [{key: item} for item in value["$each"]]
            params.pop(key)
    chain_step = ChainStep(id=step.id, action=step.action, params=params, items=items, scope=scope)
    estimate = estimate_step(db, chain_step, catalog, previous)
    details = describe_step(db, chain_step, catalog, language)
    return StepCheck(step=chain_step.model_copy(update={"estimate": estimate, "details": details}))
