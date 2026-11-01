# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Deterministic effects earlier plan steps have on a later self-claim."""

from collections.abc import Sequence
from dataclasses import dataclass

from pydantic import JsonValue

from datakeel.core.errors import NotFoundError, ValidationError
from datakeel.core.intent_models import ChainStep
from datakeel.core.production_models import Project
from datakeel.storage.database import Database
from datakeel.storage.production_queries import project_for_params


@dataclass(frozen=True)
class ClaimEffects:
    """The effective project and the work already reserved by earlier steps."""

    project: Project
    load_delta: int
    prior_claims: int
    reserved_tasks: frozenset[str]


def _concrete(step: ChainStep) -> dict[str, JsonValue]:
    params = {key: value for key, value in step.params.items() if not isinstance(value, dict)}
    return {**params, **(step.items[0] if step.items else {})}


def _project_id(db: Database, step: ChainStep) -> str | None:
    try:
        with db.session() as session:
            return project_for_params(session, _concrete(step))
    except (NotFoundError, ValidationError):
        return None


def _tasks(step: ChainStep) -> tuple[str, ...]:
    found: list[str] = []
    for entry in [{**step.params, **item} for item in step.items] or [step.params]:
        value = entry.get("task_ids")
        listed = value if isinstance(value, list) else [value]
        found += [item for item in listed if isinstance(item, str)]
    return tuple(dict.fromkeys(found))


def _stage(step: ChainStep) -> str:
    stage = step.params.get("stage")
    return stage if isinstance(stage, str) and stage else "annotation"


def _configure(project: Project, step: ChainStep) -> Project:
    if step.action == "upgrade_project":
        tier = step.params.get("workflow_tier")
        return (
            project.model_copy(update={"workflow_tier": tier}) if isinstance(tier, str) else project
        )
    updates: dict[str, object] = {}
    for field in ("dispatch_strategy", "max_active_tasks"):
        value = step.params.get(field)
        if value is not None:
            updates[field] = value
    cleared = step.params.get("clear")
    if isinstance(cleared, list) and "max_active_tasks" in cleared:
        updates["max_active_tasks"] = None
    return project.model_copy(update=updates)


def claim_effects(
    db: Database,
    project: Project,
    actor: str,
    stage: str,
    package: str | None,
    earlier: Sequence[ChainStep],
) -> ClaimEffects:
    """Replay only the certain effects relevant to a claim, leaving all other state untouched."""
    effective = project
    load_delta, prior_claims = 0, 0
    reserved: set[str] = set()
    for step in earlier:
        if _project_id(db, step) != project.id:
            continue
        if step.action in {"configure_project", "upgrade_project"}:
            effective = _configure(effective, step)
            continue
        if _stage(step) != stage:
            continue
        if step.action == "claim_task":
            load_delta += 1
            previous_package = step.params.get("package_id")
            if package is None or previous_package in (None, package):
                prior_claims += 1
        elif step.action == "assign_tasks":
            tasks = _tasks(step)
            reserved.update(tasks)
            if step.params.get("actor") == actor:
                load_delta += len(tasks)
    return ClaimEffects(effective, load_delta, prior_claims, frozenset(reserved))
