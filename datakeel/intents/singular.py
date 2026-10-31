# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""A request about one task that matches several: ask which one, never act on all of them.

"我标好的那条帮我交上去" names one task; when the person has two saved tasks the reply lists
both by project and list number and asks, instead of handing in every one.
"""

import re

from pydantic import JsonValue

from datakeel.core.errors import NotFoundError
from datakeel.core.intent_models import Candidate, Clarification
from datakeel.intents.catalog import EntityCatalog
from datakeel.intents.describe import task_positions
from datakeel.storage.database import Database
from datakeel.storage.production_queries import get_task

ONE_TASK = re.compile(
    r"那条|这条|那一条|这一条|那个任务|这个任务|\b(?:the|that|this|my) (?:one|task)\b(?!s)",
    re.IGNORECASE,
)


def says_one(text: str) -> bool:
    """The words point at a single task ("那条", "that task")."""
    return ONE_TASK.search(text) is not None


def which_task(
    db: Database, ids: list[str], catalog: EntityCatalog, action: str, language: str
) -> Clarification:
    """Offer every matching task by its project and list number."""
    positions = task_positions(db, list[JsonValue](ids))
    offered: list[Candidate] = []
    for task_id, position in zip(ids, positions, strict=True):
        try:
            project = catalog.get("project", get_task(db, task_id).project_id)
        except NotFoundError:
            project = None
        label = f"{project.label} {position}" if project is not None else position
        offered.append(Candidate(id=task_id, label=label, kind="task"))
    question = (
        f"符合的任务有 {len(ids)} 条, 是哪一条?"
        if language == "zh"
        else f"{len(ids)} tasks match; which one do you mean?"
    )
    return Clarification(question=question, action=action, fields=["task_id"], candidates=offered)
