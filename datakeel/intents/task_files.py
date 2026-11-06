# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Tasks named by the file they show: "dock-04 那张过了", "I'm done with the dock-03 one".

A task is one file of its project's dataset, so a file name the words give, with or without
its extension, finds the task in any project the speaker can see. Several matches are asked.
"""

import re

from pydantic import JsonValue

from datakeel.actions.parameters import PARAMETER_TYPES
from datakeel.core.errors import NotFoundError
from datakeel.core.intent_models import Clarification
from datakeel.dataset_store.dataset_service import list_files
from datakeel.intents.catalog import EntityCatalog
from datakeel.intents.drafts import DraftStep
from datakeel.intents.singular import which_task
from datakeel.intents.task_scope import task_number
from datakeel.storage.database import Database
from datakeel.storage.production_queries import get_project, list_tasks

FILE_NAME = re.compile(r"^(?=[\w.-]*[A-Za-z])(?=[\w.-]*\d)[\w.-]{2,120}$")
IDENTITY = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


def _file_name(value: str) -> bool:
    return FILE_NAME.match(value) is not None and IDENTITY.match(value.casefold()) is None


def _tasks_showing(db: Database, said: str, catalog: EntityCatalog) -> list[str]:
    wanted = said.casefold()
    found: list[str] = []
    for entry in catalog.of("project"):
        try:
            files = list_files(db, get_project(db, entry.id).dataset_id)
            tasks = list_tasks(db, entry.id)
        except NotFoundError:
            continue
        names = {item.id: item.filename.casefold() for item in files}
        for task in tasks:
            name = names.get(task.sample_id, "")
            if name and wanted in {name, name.rsplit(".", 1)[0]}:
                found.append(task.id)
    return found


def file_task(
    db: Database, field: str, value: JsonValue, catalog: EntityCatalog, action: str, language: str
) -> JsonValue | Clarification | None:
    """The task (or tasks) a file name stands for; None when the value is not a file name."""
    if field == "task_id" and isinstance(value, str) and _file_name(value.strip()):
        found = _tasks_showing(db, value.strip(), catalog)
        if len(found) > 1:
            return which_task(db, found, catalog, action, language)
        return found[0] if found else None
    if field != "task_ids" or not isinstance(value, list) or not value:
        return None
    named = [item.strip() for item in value if isinstance(item, str) and _file_name(item.strip())]
    if len(named) != len(value):
        return None
    hits = [_tasks_showing(db, item, catalog) for item in named]
    if any(len(hit) != 1 for hit in hits):
        return None
    listed: list[JsonValue] = [hit[0] for hit in hits]
    return listed


def said_task(step: DraftStep, params: dict[str, JsonValue]) -> None:
    """A task the model named only in its words ("dock-04", "#4") is the step's task."""
    model = PARAMETER_TYPES.get(step.action)
    said = step.said.get("task_id", "").strip()
    if model is None or "task_id" not in model.model_fields or not said:
        return
    if "task_id" not in params and (task_number(said) is not None or _file_name(said)):
        params["task_id"] = said
