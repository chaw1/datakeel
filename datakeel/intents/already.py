# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""A change that is already so: the target state compared with the current one.

Every state-changing step is compared with what the platform holds now before a card is
made. When nothing would change, the person hears the current state in plain words
("吴迪的账号已经停用", "这条已经在 Peter 手上审核", "这些文件本来就没被隔离") instead of a
card to confirm. Steps without a specific comparison fall back to the shared checks.
"""

from collections.abc import Callable

from pydantic import JsonValue
from pydantic import ValidationError as ModelValidationError

from datakeel.core.errors import DatakeelError
from datakeel.core.intent_models import ChainStep
from datakeel.intents.catalog import EntityCatalog
from datakeel.intents.impossible import idle_reason
from datakeel.intents.object_edits import current_model
from datakeel.intents.plain_words import enum_label
from datakeel.intents.verify import unchanged
from datakeel.ontology.models import ObjectSet
from datakeel.storage.database import Database
from datakeel.storage.identity_store import list_users
from datakeel.storage.intent_reads import task_holders
from datakeel.storage.object_queries import evaluate

# A status change and nothing else; any other change is compared by the shared checks.
ACCOUNT_KEYS = frozenset({"operation", "user_id", "status", "request_id"})
type State = Callable[[Database, ChainStep, EntityCatalog, str], str | None]


def _name(catalog: EntityCatalog, kind: str, identifier: JsonValue) -> str:
    entry = catalog.get(kind, identifier) if isinstance(identifier, str) else None
    return entry.label if entry is not None else str(identifier)


def _account(db: Database, step: ChainStep, catalog: EntityCatalog, language: str) -> str | None:
    """Enabling or disabling an account that is already so."""
    params = step.params
    wanted = params.get("status")
    if params.get("operation") != "update" or not isinstance(wanted, str):
        return None
    user = next((item for item in list_users(db) if item.id == params.get("user_id")), None)
    if user is None or user.status != wanted or set(params) - ACCOUNT_KEYS:
        return None
    status, who = enum_label(wanted, language), _name(catalog, "user", user.id)
    if language == "zh":
        return f"{who}的账号已经是{status}状态"
    return f"{who}'s account is already {status}"


def _holder(db: Database, step: ChainStep, catalog: EntityCatalog, language: str) -> str | None:
    """Giving tasks to the person who already holds them in that stage."""
    tasks, actor = step.params.get("task_ids"), step.params.get("actor")
    stage = str(step.params.get("stage") or "annotation")
    if not isinstance(tasks, list) or not tasks or not isinstance(actor, str):
        return None
    holders = task_holders(db, [str(task) for task in tasks], stage)
    if not all(holders.get(str(task)) == actor for task in tasks):
        return None
    who, zh = _name(catalog, "user", actor), language == "zh"
    where = ("手上审核", " for review") if stage == "review" else ("手上", "")
    return (
        f"这些任务已经在{who}{where[0]}" if zh else f"those tasks are already with {who}{where[1]}"
    )


def _files(db: Database, step: ChainStep, catalog: EntityCatalog, language: str) -> str | None:
    """Quarantining files that are all quarantined, or releasing files none of which is."""
    del catalog
    zh = language == "zh"
    try:
        query = ObjectSet.model_validate(step.params.get("selection"))
        found = evaluate(db, query).objects
    except (ModelValidationError, DatakeelError):
        return None
    flags = [item.properties.get("quarantined") is True for item in found]
    if step.action == "unquarantine_files" and not any(flags):
        return "这些文件本来就没被隔离" if zh else "those files are not quarantined"
    if step.action == "quarantine_files" and flags and all(flags):
        return "这些文件已经隔离了" if zh else "those files are already quarantined"
    return None


def _model(db: Database, step: ChainStep, catalog: EntityCatalog, language: str) -> str | None:
    """A model change that leaves every setting as the catalog holds it."""
    del catalog
    wanted = step.params.get("model")
    current = current_model(db, wanted) if isinstance(wanted, dict) else None
    if current is None or current.model_dump(mode="json", exclude={"revision"}) != wanted:
        return None
    if language == "zh":
        return f"「{current.name}」现在就是这些设置"
    return f'"{current.name}" already has exactly these settings'


STATES: dict[str, State] = {
    "update_model": _model,
    "manage_users": _account,
    "assign_tasks": _holder,
    "quarantine_files": _files,
    "unquarantine_files": _files,
}


def _ids(step: ChainStep, key: str) -> set[str]:
    values = [{**step.params, **entry}.get(key) for entry in step.items or [step.params]]
    flat = [item for value in values for item in (value if isinstance(value, list) else [value])]
    return {item for item in flat if isinstance(item, str)}


def given_back(checked: list[ChainStep], idle: dict[str, str]) -> dict[str, str]:
    """A take-back whose tasks a later idle step would hand to the one holding them now.

    "收回来再交给 X" when X already holds them would only take the tasks away from X, so the
    take-back changes nothing the person wants either and is set aside with the same state.
    """
    found: dict[str, str] = {}
    for index, step in enumerate(checked):
        taken = _ids(step, "task_id") | _ids(step, "task_ids")
        if step.action != "revoke_assignment" or step.id in idle or not taken:
            continue
        back = (
            idle[later.id]
            for later in checked[index + 1 :]
            if later.id in idle
            and later.action == "assign_tasks"
            and taken <= _ids(later, "task_ids")
        )
        if (state := next(back, None)) is not None:
            found[step.id] = state
    return found


def already_state(
    db: Database, step: ChainStep, catalog: EntityCatalog, language: str
) -> str | None:
    """The current state in words when the step would change nothing; None otherwise."""
    check = STATES.get(step.action)
    found = check(db, step, catalog, language) if check and not step.items else None
    if found is not None:
        return found
    return idle_reason(step.action, language) if unchanged(db, step) else None
