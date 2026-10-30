# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Per-task production actions run concurrently without table-wide locks or deadlocks."""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

from sqlalchemy import text

from datakeel.core.models import utcnow
from datakeel.core.production_models import ProductionTask
from datakeel.storage.action_locks import ROW_SCOPED_ACTIONS
from datakeel.storage.production_queries import project_progress
from datakeel.storage.production_reaper import reap_expired_leases
from tests.production_team_ops import claim, failure, save, set_deadline, team_project
from tests.production_team_support import ServiceRunner

if TYPE_CHECKING:
    from datakeel.storage.database import Database


def test_only_single_task_actions_skip_the_table_wide_lock() -> None:
    """Batch, project, catalog and export actions keep the predicate lock."""
    assert (
        frozenset(
            {
                "claim_task",
                "release_task",
                "heartbeat",
                "save_revision",
                "submit_task",
                "review_task",
            }
        )
        == ROW_SCOPED_ACTIONS
    )


def test_saving_does_not_wait_for_a_held_action_table_lock(db: Database) -> None:
    """On PostgreSQL a save completes while another transaction holds the action table lock."""
    project, _tasks = team_project(db, count=2)
    runner = ServiceRunner(db)
    task = ProductionTask.model_validate(
        runner("claim_task", {"project_id": project.id}, "annotator-a").root, extra="ignore"
    )
    values = {
        "task_id": task.id,
        "previous_revision_id": None,
        "annotation": {
            "sample_id": task.sample_id,
            "annotator_id": "annotator-a",
            "labels": ["cat"],
        },
    }
    if db.sqlite:
        runner("save_revision", values, "annotator-a")
    else:
        outcome: list[Exception | None] = []
        with db.engine.connect() as holder:
            # Receipts still append lineage events, so only the predicate tables are held here.
            holder.execute(
                text("LOCK TABLE datasets, versions, file_states IN SHARE ROW EXCLUSIVE MODE")
            )
            worker = threading.Thread(
                target=lambda: outcome.append(
                    failure(lambda: runner("save_revision", values, "annotator-a"))
                )
            )
            worker.start()
            worker.join(timeout=20)
            finished = not worker.is_alive()
            holder.rollback()
        worker.join(timeout=60)
        assert finished, "save_revision waited for the table-wide action lock"
        assert outcome == [None], outcome
    assert (
        ProductionTask.model_validate(
            runner("submit_task", {"task_id": task.id}, "annotator-a").root, extra="ignore"
        ).state
        == "submitted"
    )


def test_concurrent_claims_and_reaping_keep_exact_counters(db: Database) -> None:
    """Claims racing a reaper over several packages never deadlock and counters stay exact."""
    project, tasks = team_project(db, count=24, package_size=3)
    held = [claim(db, project.id, f"holder-{index}").id for index in range(8)]
    for index, task_id in enumerate(held):
        save(db, task_id, f"holder-{index}")
        set_deadline(db, task_id, -1)
    errors: list[BaseException] = []
    barrier = threading.Barrier(5)

    def claimer(index: int) -> None:
        try:
            barrier.wait()
            for _ in range(3):
                claim(db, project.id, f"claimer-{index}")
        except BaseException as error:  # noqa: BLE001  # Surface thread failures to the test.
            errors.append(error)

    def reaper() -> None:
        try:
            barrier.wait()
            reap_expired_leases(db, now=utcnow())
        except BaseException as error:  # noqa: BLE001  # Surface thread failures to the test.
            errors.append(error)

    threads = [threading.Thread(target=claimer, args=(index,)) for index in range(4)]
    threads.append(threading.Thread(target=reaper))
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=120)
    assert not errors, errors
    counts = {item.state: item.count for item in project_progress(db, project.id).counts}
    assert sum(counts.values()) == len(tasks)
    assert (counts["in_progress"], counts["pending"]) == (12, len(tasks) - 12)
    assert reap_expired_leases(db).released == 0
