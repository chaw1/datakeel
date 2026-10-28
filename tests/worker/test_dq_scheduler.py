# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Injected UTC clocks, concurrent schedule uniqueness and ordinary lease fencing."""

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from typing import Literal

import pytest
from sqlalchemy import func, select

from datakeel.core.dq_cron import cron_matches, latest_match, validate_cron
from datakeel.core.dq_models import DqResult, DqRule
from datakeel.core.dq_monitor import DqCompletion, DqRun
from datakeel.core.errors import ConflictError, NotFoundError, ValidationError
from datakeel.storage.database import Database, ShardRow, TaskRow, VersionRow
from datakeel.storage.dq_jobs import schedule_due, schedule_rule
from datakeel.storage.dq_reads import get_run, read_issues, read_results
from datakeel.storage.dq_rows import DqRunRow, DqWebhookRow
from datakeel.storage.dq_store import delete_rule, upsert_rule
from datakeel.storage.dq_views import read_summary
from datakeel.worker.queue import DatabaseQueue, Lease
from tests.storage.test_dq_store import definition


@pytest.mark.parametrize(
    "expression",
    [
        "* * *",
        "60 * * * *",
        "*/0 * * * *",
        "1-0 * * * *",
        "1/x * * * *",
        "* * * * * *",
        "* * * * MON",
    ],
)
def test_invalid_cron_is_rejected(expression: str) -> None:
    """Reject malformed syntax rather than silently scheduling a different period."""
    with pytest.raises(ValidationError):
        validate_cron(expression)


def test_cron_ranges_steps_weekdays_and_standard_day_or() -> None:
    """Numeric lists and Sunday aliases follow standard five-field cron semantics."""
    monday = datetime(2026, 1, 5, 9, 15, tzinfo=UTC)
    assert validate_cron(" */15  9-17 * * 1-5 ") == "*/15 9-17 * * 1-5"
    assert cron_matches("*/15 9-17 * * 1-5", monday)
    assert not cron_matches("0,30 9-17 * * 1-5", monday)
    assert cron_matches("15 9 1 * 1", monday)
    sunday = datetime(2026, 1, 4, 9, 15, tzinfo=UTC)
    assert cron_matches("15 9 * * 7", sunday)
    assert not cron_matches("15 9 * 2 *", sunday)


def test_two_schedulers_use_one_slot_and_coalesce_missed_minutes(db: Database) -> None:
    """Both workers enqueue one task for the current minute; skipped hours collapse into one."""
    rule = definition().model_copy(update={"cron": "0 * * * *"})
    with db.session() as session:
        upsert_rule(session, rule, None, "reviewer")
        session.commit()
    now = datetime(2026, 1, 1, 9, tzinfo=UTC)

    def tick(_index: int) -> tuple[DqRun, ...]:
        return schedule_due(db, now)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(tick, range(2)))
    assert results[0][0].task_id == results[1][0].task_id
    assert schedule_due(db, now + timedelta(minutes=5)) == ()
    next_slot = schedule_due(db, now + timedelta(hours=4))
    assert next_slot[0].task_id != results[0][0].task_id
    with db.session() as session:
        assert session.scalar(select(func.count()).select_from(TaskRow)) == 2
        assert session.scalar(select(func.count()).select_from(VersionRow)) == 1
        assert session.scalar(select(func.count()).select_from(DqRunRow)) == 2


def test_rule_revision_changes_schedule_identity_and_disabled_rejected(db: Database) -> None:
    """New revisions use independent slot identities; disabled rules cannot run."""
    with db.session() as session:
        rule = upsert_rule(session, definition(), None, "reviewer")
        first = schedule_rule(session, rule.id, "manual:one")
        assert schedule_rule(session, rule.id, "manual:one") == first
        upsert_rule(session, rule, 1, "reviewer")
        assert schedule_rule(session, rule.id, "manual:one").task_id != first.task_id
        upsert_rule(session, rule.model_copy(update={"enabled": False}), 2, "reviewer")
        with pytest.raises(ValidationError):
            schedule_rule(session, rule.id, "manual:two")
        with pytest.raises(NotFoundError):
            get_run(session, "absent")
        session.commit()


def test_reaped_old_lease_cannot_publish_result_or_incident(db: Database) -> None:
    """Only the fresh ordinary shard token can publish quality facts."""
    with db.session() as session:
        rule = upsert_rule(session, definition(), None, "reviewer")
        run = schedule_rule(session, rule.id, "manual:fencing")
        session.commit()
    queue = DatabaseQueue(db, lease_seconds=1)
    stale = queue.claim()
    assert stale is not None
    with db.session() as session:
        shard = session.get(ShardRow, stale.shard_id)
        assert shard is not None
        shard.heartbeat_at = 0
        session.commit()
    assert queue.reap() == 1
    fresh = queue.claim()
    assert fresh is not None
    completion = DqCompletion(run_id=run.id, result=DqResult(rule_id=rule.id, status="failed"))
    assert not queue.finish(stale, [], [], evidence=completion)
    assert read_results(db, rule.id) == ()
    assert read_issues(db) == ()
    assert queue.finish(fresh, [], [], evidence=completion)
    assert len(read_results(db, rule.id)) == 1
    assert len(read_issues(db)) == 1
    with db.session() as session:
        assert get_run(session, run.id).state == "COMPLETED"
        assert session.scalar(select(func.count()).select_from(VersionRow)) == 1


def test_mismatched_result_rolls_back_fenced_completion(db: Database) -> None:
    """A leased worker cannot attach another rule's result to its job."""
    with db.session() as session:
        rule = upsert_rule(session, definition(), None, "reviewer")
        run = schedule_rule(session, rule.id, "manual:wrong")
        session.commit()
    queue = DatabaseQueue(db)
    lease = queue.claim()
    assert lease is not None
    with pytest.raises(ConflictError):
        queue.finish(
            lease,
            [],
            [],
            evidence=DqCompletion(run_id=run.id, result=DqResult(rule_id="wrong", status="passed")),
        )
    assert queue.finish(
        lease,
        [],
        [],
        evidence=DqCompletion(
            run_id=run.id, result=DqResult(rule_id=rule.id, status="baseline_insufficient")
        ),
    )
    assert read_issues(db) == ()


def test_two_workers_claim_same_slot_once_and_merge_distinct_failures(db: Database) -> None:
    """One slot has one lease and separate jobs serialize their shared incident update."""
    with db.session() as session:
        upsert_rule(session, definition(), None, "reviewer")
        first = schedule_rule(session, "orders-required", "same-slot")
        session.commit()
    queue = DatabaseQueue(db)

    def claim(_index: int) -> Lease | None:
        return queue.claim()

    with ThreadPoolExecutor(max_workers=2) as pool:
        claims = list(pool.map(claim, range(2)))
    leases = [lease for lease in claims if lease is not None]
    assert len(leases) == 1
    with db.session() as session:
        second = schedule_rule(session, "orders-required", "next-slot")
        session.commit()
    other = queue.claim()
    assert other is not None
    jobs = [(leases[0], first.id), (other, second.id)]

    # Equal observation times: commit order, not construction order, decides the latest result.
    instant = datetime(2026, 1, 1, tzinfo=UTC)

    def finish(job: tuple[Lease, str]) -> bool:
        lease, run_id = job
        result = DqResult(rule_id="orders-required", status="failed", started_at=instant)
        return queue.finish(lease, [], [], evidence=DqCompletion(run_id=run_id, result=result))

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert all(pool.map(finish, jobs))
    assert len(read_issues(db)) == 1
    assert read_issues(db)[0].failures == 2


def test_old_revision_result_is_historical_without_current_alert(db: Database) -> None:
    """An edited rule retains old jobs while old failures cannot reopen current issues."""
    with db.session() as session:
        rule = upsert_rule(session, definition(), None, "reviewer")
        run = schedule_rule(session, rule.id, "before-edit")
        upsert_rule(session, rule, 1, "reviewer")
        session.commit()
    queue = DatabaseQueue(db)
    lease = queue.claim()
    assert lease is not None
    assert queue.finish(
        lease,
        [],
        [],
        evidence=DqCompletion(
            run_id=run.id, result=DqResult(rule_id=rule.id, rule_revision=1, status="failed")
        ),
    )
    assert len(read_results(db, rule.id)) == 1
    assert read_issues(db) == ()


def test_scheduler_rejects_naive_clock(db: Database) -> None:
    """Do not guess a process timezone for a clock missing UTC offset information."""
    with pytest.raises(ValidationError, match="aware clock"):
        schedule_due(db, datetime(2026, 1, 1))  # noqa: DTZ001  # Invalid clock is the test input.


def test_out_of_order_old_failure_does_not_override_newer_pass(db: Database) -> None:
    """Completing an older observation late retains history without a stale incident."""
    with db.session() as session:
        rule = upsert_rule(session, definition(), None, "reviewer")
        older = schedule_rule(session, rule.id, "older")
        newer = schedule_rule(session, rule.id, "newer")
        session.commit()
    queue = DatabaseQueue(db)
    first, second = queue.claim(), queue.claim()
    assert first is not None
    assert second is not None
    instant = datetime(2026, 1, 1, tzinfo=UTC)
    assert queue.finish(
        second,
        [],
        [],
        evidence=DqCompletion(
            run_id=newer.id,
            result=DqResult(
                rule_id=rule.id, status="passed", started_at=instant + timedelta(minutes=1)
            ),
        ),
    )
    assert queue.finish(
        first,
        [],
        [],
        evidence=DqCompletion(
            run_id=older.id, result=DqResult(rule_id=rule.id, status="failed", started_at=instant)
        ),
    )
    assert [result.status for result in read_results(db, rule.id)] == ["passed", "failed"]
    assert read_issues(db) == ()


def test_equal_clock_observations_use_committed_sequence_for_latest(db: Database) -> None:
    """Equal injected timestamps follow completion order, independent of random IDs."""
    with db.session() as session:
        rule = upsert_rule(session, definition(), None, "reviewer")
        first_run = schedule_rule(session, rule.id, "one")
        last_run = schedule_rule(session, rule.id, "two")
        session.commit()
    queue = DatabaseQueue(db)
    first, second = queue.claim(), queue.claim()
    assert first is not None
    assert second is not None
    instant = datetime(2026, 1, 1, tzinfo=UTC)
    assert queue.finish(
        first,
        [],
        [],
        evidence=DqCompletion(
            run_id=first_run.id,
            result=DqResult(id="z-first", rule_id=rule.id, status="failed", started_at=instant),
        ),
    )
    assert queue.finish(
        second,
        [],
        [],
        evidence=DqCompletion(
            run_id=last_run.id,
            result=DqResult(id="a-second", rule_id=rule.id, status="passed", started_at=instant),
        ),
    )
    assert [result.status for result in read_results(db, rule.id)] == ["passed", "failed"]
    assert read_issues(db)[0].status == "recovered"


def test_run_view_reflects_claimed_and_terminal_task_state(db: Database) -> None:
    """A run view follows its actual task lifecycle without exposing lease credentials."""
    with db.session() as session:
        rule = upsert_rule(session, definition(), None, "reviewer")
        run = schedule_rule(session, rule.id, "lifecycle")
        session.commit()
        assert get_run(session, run.id).state == "QUEUED"
    queue = DatabaseQueue(db)
    lease = queue.claim()
    assert lease is not None
    with db.session() as session:
        view = get_run(session, run.id)
        assert view.state == "RUNNING"
        assert "owner" not in view.model_dump()
    assert queue.finish(
        lease,
        [],
        [],
        evidence=DqCompletion(run_id=run.id, result=DqResult(rule_id=rule.id, status="passed")),
    )
    with db.session() as session:
        assert get_run(session, run.id).state == "COMPLETED"


def test_exhausted_worker_emits_one_error_observation_incident_and_alert(db: Database) -> None:
    """A dead worker produces monitored infrastructure failure instead of permanent pending."""
    with db.session() as session:
        rule = upsert_rule(session, definition(), None, "reviewer")
        run = schedule_rule(session, rule.id, "exhausted-observation")
        session.commit()
    queue = DatabaseQueue(db, max_attempts=1)
    lease = queue.claim()
    assert lease is not None
    with db.session() as session:
        shard = session.get(ShardRow, lease.shard_id)
        assert shard is not None
        shard.heartbeat_at = 0
        session.commit()
    assert queue.reap() == 1
    assert queue.reap() == 0
    assert not queue.finish(lease, [], [], error="obsolete attempt")
    assert read_results(db, rule.id)[0].status == "error"
    assert read_results(db, rule.id)[0].message == (
        "Worker retries exhausted or task failed before publication"
    )
    assert read_summary(db).errors == 1
    assert read_summary(db).score == 0
    assert len(read_issues(db)) == 1
    with db.session() as session:
        assert get_run(session, run.id).state == "FAILED"
        assert session.scalar(select(func.count()).select_from(DqWebhookRow)) == 1


def test_user_cancellation_does_not_claim_quality_failure(db: Database) -> None:
    """Cancelling monitoring work retains cancellation without a data-quality verdict."""
    with db.session() as session:
        rule = upsert_rule(session, definition(), None, "reviewer")
        run = schedule_rule(session, rule.id, "cancelled-observation")
        session.commit()
    queue = DatabaseQueue(db)
    assert queue.claim() is not None
    assert queue.cancel(run.task_id)
    assert read_results(db, rule.id) == ()
    assert read_issues(db) == ()
    with db.session() as session:
        assert get_run(session, run.id).state == "CANCELLED"
        assert session.scalar(select(func.count()).select_from(DqWebhookRow)) == 0


@pytest.mark.parametrize("change", ["edit", "disable", "delete"])
def test_exhausted_old_revision_is_history_without_current_incident(
    db: Database,
    change: str,
) -> None:
    """Retiring or replacing a frozen job retains its error without current alerts."""
    with db.session() as session:
        rule = upsert_rule(session, definition(), None, "reviewer")
        run = schedule_rule(session, rule.id, "obsolete-observation")
        if change == "delete":
            delete_rule(session, rule.id, 1, "reviewer")
        else:
            upsert_rule(
                session, rule.model_copy(update={"enabled": change != "disable"}), 1, "reviewer"
            )
        session.commit()
    queue = DatabaseQueue(db, max_attempts=1)
    lease = queue.claim()
    assert lease is not None
    with db.session() as session:
        shard = session.get(ShardRow, lease.shard_id)
        assert shard is not None
        shard.heartbeat_at = 0
        session.commit()
    assert queue.reap() == 1
    assert len(read_results(db, rule.id)) == 1
    assert read_issues(db) == ()
    with db.session() as session:
        assert get_run(session, run.id).state == "FAILED"
        assert session.scalar(select(func.count()).select_from(DqWebhookRow)) == 0


def test_late_exhausted_job_does_not_override_newer_pass(db: Database) -> None:
    """A late infrastructure failure remains historical when a newer observation passed."""
    instant = datetime(2026, 1, 1, tzinfo=UTC)
    with db.session() as session:
        rule = upsert_rule(session, definition(), None, "reviewer")
        older = schedule_rule(session, rule.id, "old-exhaustion")
        newer = schedule_rule(session, rule.id, "new-pass")
        task = session.get(TaskRow, older.task_id)
        assert task is not None
        task.created_at = instant.timestamp()
        session.commit()
    queue = DatabaseQueue(db, max_attempts=1)
    stale, current = queue.claim(), queue.claim()
    assert stale is not None
    assert current is not None
    assert queue.finish(
        current,
        [],
        [],
        evidence=DqCompletion(
            run_id=newer.id,
            result=DqResult(
                rule_id=rule.id, status="passed", started_at=instant + timedelta(minutes=1)
            ),
        ),
    )
    with db.session() as session:
        shard = session.get(ShardRow, stale.shard_id)
        assert shard is not None
        shard.heartbeat_at = 0
        session.commit()
    assert queue.reap() == 1
    assert [result.status for result in read_results(db, rule.id)] == ["passed", "error"]
    assert read_summary(db).passed == 1
    assert read_issues(db) == ()


def _accept_at(db: Database, monkeypatch: pytest.MonkeyPatch, rule: DqRule, at: datetime) -> None:
    monkeypatch.setattr("datakeel.storage.dq_store.utcnow", lambda: at)
    with db.session() as session:
        upsert_rule(session, rule, None, "reviewer")
        session.commit()


def test_missed_minutes_coalesce_into_newest_slot_within_window(
    db: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A busy or restarted worker runs the newest missed minute once; >24h misses are skipped."""
    start = datetime(2030, 1, 1, 9, tzinfo=UTC)
    _accept_at(db, monkeypatch, definition().model_copy(update={"cron": "*/15 * * * *"}), start)
    assert [run.slot for run in schedule_due(db, start)] == [start.isoformat()]
    late = schedule_due(db, start + timedelta(minutes=47, seconds=30))
    assert [run.slot for run in late] == [(start + timedelta(minutes=45)).isoformat()]
    assert schedule_due(db, start + timedelta(minutes=48)) == ()
    resumed = schedule_due(db, start + timedelta(days=3, minutes=7))
    assert [run.slot for run in resumed] == [(start + timedelta(days=3)).isoformat()]
    with db.session() as session:
        assert session.scalar(select(func.count()).select_from(DqRunRow)) == 3


def test_catch_up_never_schedules_minutes_before_revision_acceptance(
    db: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A daily rule accepted after today's minute waits for tomorrow, then catches up once."""
    accepted = datetime(2030, 1, 1, 9, 30, tzinfo=UTC)
    _accept_at(db, monkeypatch, definition().model_copy(update={"cron": "0 9 * * *"}), accepted)
    assert schedule_due(db, accepted + timedelta(hours=1)) == ()
    tomorrow = datetime(2030, 1, 2, 9, tzinfo=UTC)
    restarted = schedule_due(db, tomorrow + timedelta(hours=2))
    assert [run.slot for run in restarted] == [tomorrow.isoformat()]
    assert schedule_due(db, tomorrow + timedelta(hours=3)) == ()


def test_latest_match_skips_hours_days_and_month_boundaries() -> None:
    """Backward search honours each field and the window's lower bound."""
    latest = datetime(2030, 3, 2, 10, 5, tzinfo=UTC)
    week = timedelta(days=7)
    assert latest_match("0 9 1 * *", latest, latest - week) == datetime(2030, 3, 1, 9, tzinfo=UTC)
    assert latest_match("30 23 * 2 *", latest, latest - week) == datetime(
        2030, 2, 28, 23, 30, tzinfo=UTC
    )
    assert latest_match("*/20 * * * *", latest, latest - week) == datetime(
        2030, 3, 2, 10, tzinfo=UTC
    )
    assert latest_match("0 9 1 * *", latest, latest - timedelta(hours=20)) is None
    assert latest_match("5 10 * * *", latest, latest) == latest


def test_consecutive_failures_alert_once_and_state_changes_alert_again(db: Database) -> None:
    """Merged failures raise the issue count only; recovery and relapse each send one alert."""
    with db.session() as session:
        rule = upsert_rule(session, definition(), None, "reviewer")
        session.commit()
    queue = DatabaseQueue(db)
    instant = datetime(2030, 1, 1, tzinfo=UTC)
    outcomes: tuple[Literal["passed", "failed", "error"], ...] = (
        "failed",
        "failed",
        "error",
        "passed",
        "passed",
        "failed",
    )
    for minute, status in enumerate(outcomes):
        with db.session() as session:
            run = schedule_rule(session, rule.id, f"alert-{minute}")
            session.commit()
        lease = queue.claim()
        assert lease is not None
        result = DqResult(
            rule_id=rule.id, status=status, started_at=instant + timedelta(minutes=minute)
        )
        assert queue.finish(lease, [], [], evidence=DqCompletion(run_id=run.id, result=result))
    with db.session() as session:
        events = [
            json.loads(row.body)["event_type"]
            for row in session.scalars(select(DqWebhookRow).order_by(DqWebhookRow.due_at))
        ]
    assert events == ["quality.failed", "quality.recovered", "quality.failed"]
    assert read_issues(db)[0].failures == 4
