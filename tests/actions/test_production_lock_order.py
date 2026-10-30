# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Every action takes its table locks before any task row, so managers and holders never deadlock.

PostgreSQL lock-mode conflicts follow the documented table ("Conflicting Lock Modes",
https://www.postgresql.org/docs/current/explicit-locking.html).
"""

from __future__ import annotations

import re
import threading
import time
from collections import Counter
from typing import TYPE_CHECKING

from sqlalchemy import event, text

from datakeel.actions import service
from datakeel.actions.models import ApprovalDecision, ExecuteRequest
from datakeel.core.errors import DatakeelError
from datakeel.core.production_models import ProductionTask
from datakeel.storage.action_locks import (
    PREDICATE_TABLES,
    ROW_SCOPED_ACTIONS,
    TABLE_WIDE_MODE,
    table_locks,
)
from datakeel.storage.production_queries import list_tasks, project_progress
from tests.production_team_ops import failure, team_project
from tests.production_team_support import ServiceRunner

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from sqlalchemy import Connection

    from datakeel.actions.models import ActionPlan, ActionRun
    from datakeel.storage.database import Database

_EXCLUSIVE = {"EXCLUSIVE", "ACCESS EXCLUSIVE"}
CONFLICTS = {
    "ROW EXCLUSIVE": {"SHARE", "SHARE ROW EXCLUSIVE"} | _EXCLUSIVE,
    "SHARE": {"ROW EXCLUSIVE", "SHARE UPDATE EXCLUSIVE", "SHARE ROW EXCLUSIVE"} | _EXCLUSIVE,
    "SHARE ROW EXCLUSIVE": {
        "ROW EXCLUSIVE",
        "SHARE UPDATE EXCLUSIVE",
        "SHARE",
        "SHARE ROW EXCLUSIVE",
    }
    | _EXCLUSIVE,
}
_WRITE = re.compile(r'^\s*(?:INSERT\s+INTO|UPDATE|DELETE\s+FROM)\s+"?(\w+)', re.IGNORECASE)


def _written(db: Database, operation: Callable[[], object]) -> set[str]:
    tables: set[str] = set()

    def record(*arguments: object) -> None:
        match = _WRITE.match(str(arguments[2]))
        if match:
            tables.add(match.group(1).lower())

    event.listen(db.engine, "before_cursor_execute", record)
    try:
        operation()
    finally:
        event.remove(db.engine, "before_cursor_execute", record)
    return tables


def _task(details: Mapping[str, object]) -> ProductionTask:
    return ProductionTask.model_validate(details, extra="ignore")


def _save_values(task: ProductionTask, actor: str, head: str | None) -> dict[str, object]:
    return {
        "task_id": task.id,
        "previous_revision_id": head,
        "annotation": {"sample_id": task.sample_id, "annotator_id": actor, "labels": ["cat"]},
    }


def _execute(db: Database, plan: ActionPlan, actor: str) -> ActionRun:
    if plan.requires_approval:
        service.approve_plan(
            db, plan.id, ApprovalDecision(approve=True, plan_digest=plan.plan_digest, actor=actor)
        )
    run = service.execute_plan(
        db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest, actor=actor)
    )
    assert run.status == "SUCCEEDED", run.error
    return run


def test_single_task_actions_lock_every_predicate_table_they_write_up_front(
    db: Database,
) -> None:
    """Each per-task action's up-front lock covers its receipt writes and blocks table-wide work.

    The mode must conflict with the table-wide lock (so a manager action and a receipt writer
    never interleave) and not with itself (so annotators stay concurrent).
    """
    project, _tasks = team_project(db, count=3)
    runner = ServiceRunner(db)
    written: dict[str, set[str]] = {}

    def run(action: str, values: Mapping[str, object], actor: str) -> dict[str, object]:
        result: list[dict[str, object]] = []
        written.setdefault(action, set()).update(
            _written(db, lambda: result.append(dict(runner(action, values, actor).root)))
        )
        return result[0]

    task = _task(run("claim_task", {"project_id": project.id}, "annotator-a"))
    run("heartbeat", {"task_id": task.id}, "annotator-a")
    run("save_revision", _save_values(task, "annotator-a", None), "annotator-a")
    run("submit_task", {"task_id": task.id}, "annotator-a")
    run("claim_task", {"project_id": project.id, "stage": "review"}, "reviewer-b")
    head = next(
        item for item in list_tasks(db, project.id) if item.id == task.id
    ).latest_revision_id
    run(
        "review_task",
        {"task_id": task.id, "revision_id": head, "decision": "approve"},
        "reviewer-b",
    )
    other = _task(run("claim_task", {"project_id": project.id}, "annotator-a"))
    run("release_task", {"task_id": other.id}, "annotator-a")
    assert set(written) == ROW_SCOPED_ACTIONS
    for action, tables in sorted(written.items()):
        locked, mode = table_locks(action)
        assert "lineage_events" in tables, action
        assert tables & set(PREDICATE_TABLES) <= set(locked), (action, tables, locked)
        assert mode in CONFLICTS[TABLE_WIDE_MODE], (action, mode)
        assert mode not in CONFLICTS[mode], (action, mode)
    assert table_locks("assign_tasks") == (PREDICATE_TABLES, TABLE_WIDE_MODE)
    assert table_locks(None) == (PREDICATE_TABLES, TABLE_WIDE_MODE)


def _wait_for_lineage_waiter(connection: Connection, deadline: float) -> None:
    while time.monotonic() < deadline:
        waiting = connection.execute(
            text(
                "SELECT count(*) FROM pg_locks WHERE NOT granted AND locktype = 'relation' "
                "AND relation = 'lineage_events'::regclass"
            )
        ).scalar_one()
        if waiting:
            return
        time.sleep(0.05)
    message = "The save never queued behind the held table lock"
    raise AssertionError(message)


def test_save_queues_at_the_table_lock_before_locking_its_task_row(db: Database) -> None:
    """While a table-wide action holds its locks, a waiting save must not hold the task row."""
    project, _tasks = team_project(db, count=2)
    runner = ServiceRunner(db)
    task = _task(runner("claim_task", {"project_id": project.id}, "annotator-a").root)
    plan = runner.plan("save_revision", _save_values(task, "annotator-a", None), "annotator-a")
    if db.sqlite:
        _execute(db, plan, "annotator-a")
        return
    outcome: list[Exception | None] = []
    with db.engine.connect() as holder:
        holder.execute(text(f"LOCK TABLE {', '.join(PREDICATE_TABLES)} IN {TABLE_WIDE_MODE} MODE"))
        saver = threading.Thread(
            target=lambda: outcome.append(failure(lambda: _execute(db, plan, "annotator-a")))
        )
        saver.start()
        _wait_for_lineage_waiter(holder, time.monotonic() + 20)
        # The manager's next step is locking the task row; it must not find the saver there.
        row_free = failure(
            lambda: holder.execute(
                text("SELECT id FROM production_tasks WHERE id = :task FOR UPDATE NOWAIT"),
                {"task": task.id},
            ).all()
        )
        holder.rollback()
    saver.join(timeout=60)
    assert row_free is None, row_free
    assert outcome == [None], outcome


class _Race:
    """A holder and a manager work on one task; each round forces the dangerous interleaving.

    Per round the manager prepares a revoke, lets the holder save, and executes the revoke
    exactly while the holder holds the task row but has not yet written its receipt. With the
    lock order fixed the revoke waits, then fails cleanly on its stale plan; with row locks taken
    before table locks the two transactions deadlock. The manager then revokes and assigns the
    task back for real while the holder is idle, so every round also exercises both actions.
    """

    def __init__(self, db: Database, task: ProductionTask, rounds: int) -> None:
        """Bind both participants to one database and one claimed task."""
        self.db, self.task, self.rounds = db, task, rounds
        self.runner = ServiceRunner(db)
        self.unexpected: list[BaseException] = []
        self.outcomes: Counter[str] = Counter()
        self.turn, self.inside, self.saved = threading.Event(), threading.Event(), threading.Event()

    def pause_inside_row_lock(self, *arguments: object) -> None:
        """Hold the holder's task row before its receipt: the window table locks must not enter."""
        statement = str(arguments[2]).lstrip().upper()
        if (
            threading.current_thread().name == "holder"
            and statement.startswith("UPDATE PRODUCTION_TASKS")
            and not self.inside.is_set()
        ):
            self.inside.set()
            time.sleep(0.05)

    def execute(self, name: str, plan: ActionPlan, actor: str) -> ActionRun | None:
        """Count domain refusals by kind; keep database failures such as deadlocks apart."""
        try:
            run = _execute(self.db, plan, actor)
        except DatakeelError as error:
            self.outcomes[f"{name}:{type(error).__name__}"] += 1
            return None
        except BaseException as error:  # noqa: BLE001  # Surface database failures to the test.
            self.unexpected.append(error)
            return None
        self.outcomes[f"{name}:ok"] += 1
        return run

    def holder(self) -> None:
        """Save once per round when the manager says so, tracking the revision head."""
        head: str | None = None
        for _ in range(self.rounds):
            if not self.turn.wait(timeout=60):
                return
            self.turn.clear()
            values = _save_values(self.task, "annotator-a", head)
            run = self.execute(
                "save", self.runner.plan("save_revision", values, "annotator-a"), "annotator-a"
            )
            if run is not None and run.receipt is not None:
                head = str(run.receipt.quality["details"]["id"])
            self.saved.set()

    def manager(self) -> None:
        """Revoke inside the holder's row lock, then revoke and assign back while it is idle."""
        reclaim = {"task_id": self.task.id, "reason": "Generated reclaim"}
        assign = {"task_ids": [self.task.id], "actor": "annotator-a"}
        for _ in range(self.rounds):
            stale = self.runner.plan("revoke_assignment", reclaim, "pm")
            self.inside.clear()
            self.saved.clear()
            self.turn.set()
            if self.inside.wait(timeout=30):
                self.outcomes["window"] += 1
                self.execute("revoke_during_save", stale, "pm")
            self.saved.wait(timeout=60)
            self.execute("revoke", self.runner.plan("revoke_assignment", reclaim, "pm"), "pm")
            self.execute("assign", self.runner.plan("assign_tasks", assign, "pm"), "pm")


def test_holder_saves_racing_manager_revoke_and_assign_never_deadlock(db: Database) -> None:
    """A manager revokes and re-assigns the task its holder is saving, round after round."""
    rounds = 10
    project, tasks = team_project(db, count=2)
    task = _task(ServiceRunner(db)("claim_task", {"project_id": project.id}, "annotator-a").root)
    race = _Race(db, task, rounds)
    threads = [
        threading.Thread(target=race.holder, name="holder"),
        threading.Thread(target=race.manager, name="manager"),
    ]
    event.listen(db.engine, "after_cursor_execute", race.pause_inside_row_lock)
    try:
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=300)
    finally:
        event.remove(db.engine, "after_cursor_execute", race.pause_inside_row_lock)
    assert race.unexpected == []
    # A reclaim plan freezes only state, round and holders, so the reclaim prepared before the
    # save waits for its row lock and then succeeds; the idle reclaim finds nothing left to take.
    assert race.outcomes == {
        "window": rounds,
        "save:ok": rounds,
        "revoke_during_save:ok": rounds,
        "revoke:NotFoundError": rounds,
        "assign:ok": rounds,
    }
    counts = {item.state: item.count for item in project_progress(db, project.id).counts}
    actual = [item.state for item in list_tasks(db, project.id)]
    assert counts == {state: actual.count(state) for state in counts}
    assert sum(counts.values()) == len(tasks)
