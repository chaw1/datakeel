# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""One effective-state projection for later claims and dispatches in a plan."""

from collections.abc import Sequence
from dataclasses import dataclass, field

from pydantic import JsonValue

from datakeel.core.errors import NotFoundError, ValidationError
from datakeel.core.intent_models import ChainStep
from datakeel.core.production_models import Project
from datakeel.storage.database import Database
from datakeel.storage.intent_reads import task_holders
from datakeel.storage.production_queries import project_for_params

UNCERTAIN_ACTIONS = frozenset(
    {"submit_task", "review_task", "reopen_task", "run_prelabel", "import_predictions"}
)
WORK_ACTIONS = frozenset({"claim_task", "assign_tasks", "release_task", "revoke_assignment"})


@dataclass(frozen=True)
class ClaimQuery:
    """The later claim or dispatch whose preconditions need the effective state."""

    project: Project
    actor: str
    person: str
    stage: str
    package: str | None


@dataclass(frozen=True)
class ClaimEffects:
    """Effective configuration, load and queue changes; uncertain effects refuse safely."""

    project: Project
    load_delta: int = 0
    prior_claims: int = 0
    reserved_tasks: frozenset[str] = frozenset()
    released_tasks: frozenset[str] = frozenset()
    uncertain: bool = False
    touched: bool = False


def _concrete(step: ChainStep) -> dict[str, JsonValue]:
    params = {key: value for key, value in step.params.items() if not isinstance(value, dict)}
    return {**params, **(step.items[0] if step.items else {})}


def _project_id(db: Database, step: ChainStep) -> str | None:
    try:
        with db.session() as session:
            return project_for_params(session, _concrete(step))
    except (NotFoundError, ValidationError):
        return None


def _tasks(step: ChainStep, keys: tuple[str, ...] = ("task_id", "task_ids")) -> tuple[str, ...]:
    found: list[str] = []
    for entry in [{**step.params, **item} for item in step.items] or [step.params]:
        for key in keys:
            value = entry.get(key)
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
    for field_name in ("dispatch_strategy", "max_active_tasks"):
        value = step.params.get(field_name)
        if value is not None:
            updates[field_name] = value
    cleared = step.params.get("clear")
    if isinstance(cleared, list) and "max_active_tasks" in cleared:
        updates["max_active_tasks"] = None
    return project.model_copy(update=updates)


@dataclass
class _Projection:
    project: Project
    load_delta: int = 0
    prior_claims: int = 0
    reserved: set[str] = field(default_factory=set[str])
    released: set[str] = field(default_factory=set[str])
    added: set[str] = field(default_factory=set[str])
    uncertain: bool = False
    touched: bool = False

    def apply(self, db: Database, query: ClaimQuery, step: ChainStep) -> None:
        if step.action in {"configure_project", "upgrade_project"}:
            self.uncertain |= step.action == "upgrade_project" and query.project.workflow_tier == (
                "personal"
            )
            self.project = _configure(self.project, step)
            return
        if step.action in UNCERTAIN_ACTIONS:
            self.touched = self.uncertain = True
            return
        if _stage(step) != query.stage or step.action not in WORK_ACTIONS:
            return
        self.touched = True
        if step.action == "claim_task":
            self._claim(query, step)
        elif step.action == "assign_tasks":
            self._assign(query.person, step)
        else:
            self._release(db, query.person, step)

    def _claim(self, query: ClaimQuery, step: ChainStep) -> None:
        if step.params.get("project_id") is None:
            self.uncertain = True
        if query.actor == query.person:
            self.load_delta += 1
        previous_package = step.params.get("package_id")
        if query.package is None or previous_package in (None, query.package):
            self.prior_claims += 1

    def _assign(self, person: str, step: ChainStep) -> None:
        tasks = _tasks(step)
        if not tasks or step.params.get("actor") is None:
            self.uncertain = True
        self.reserved.update(tasks)
        self.released.difference_update(tasks)
        if step.params.get("actor") == person:
            self.load_delta += len(tasks)
            self.added.update(tasks)

    def _release(self, db: Database, person: str, step: ChainStep) -> None:
        tasks = _tasks(step, ("task_id",))
        holders = task_holders(db, list(tasks), _stage(step))
        if not tasks:
            self.uncertain = True
        for task in tasks:
            if task in self.added:
                self.load_delta -= 1
                self.added.remove(task)
            elif holders.get(task) == person and task not in self.released:
                self.load_delta -= 1
        self.released.update(tasks)
        self.reserved.difference_update(tasks)

    def effects(self) -> ClaimEffects:
        return ClaimEffects(
            self.project,
            self.load_delta,
            self.prior_claims,
            frozenset(self.reserved),
            frozenset(self.released),
            self.uncertain,
            self.touched,
        )


def claim_effects(db: Database, query: ClaimQuery, earlier: Sequence[ChainStep]) -> ClaimEffects:
    """Replay every registered action that can affect capacity, strategy or the free queue."""
    projection = _Projection(query.project)
    for step in earlier:
        if _project_id(db, step) == query.project.id:
            projection.apply(db, query, step)
    return projection.effects()
