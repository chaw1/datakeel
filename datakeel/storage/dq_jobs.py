# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Schedule quality checks through the existing task shards and lease reaper."""

from datetime import UTC, datetime, timedelta
from hashlib import sha256

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from datakeel.core.dq_cron import latest_match
from datakeel.core.dq_models import DqRule
from datakeel.core.dq_monitor import DqRuleHistory, DqRun
from datakeel.core.errors import ValidationError
from datakeel.core.models import new_id, utcnow
from datakeel.storage.database import Database, DatasetRow, ShardRow, TaskRow, VersionRow
from datakeel.storage.dq_reads import get_run
from datakeel.storage.dq_rows import DqHistoryRow, DqRuleRow, DqRunRow
from datakeel.storage.dq_store import get_rule

# Missed minutes older than this are skipped; newer ones coalesce into one run.
CATCH_UP_WINDOW = timedelta(hours=24)


def _lock_targets(session: Session) -> None:
    if session.get_bind().dialect.name == "postgresql":
        session.execute(
            text(
                "LOCK TABLE datasets, lineage_events, versions, file_states "
                "IN SHARE ROW EXCLUSIVE MODE"
            )
        )


def _monitor_dataset(session: Session, source_id: str) -> tuple[str, str]:
    identifier = "dq-monitor:" + sha256(source_id.encode()).hexdigest()[:24]
    dataset = session.get(DatasetRow, identifier)
    if dataset is None:
        dataset = DatasetRow(
            id=identifier,
            name="Quality monitoring",
            files=[],
            metadata_values={"internal_quality_monitor": True},
        )
        session.add(dataset)
        session.flush()
        version = VersionRow(dataset_id=identifier, manifest=[])
        session.add(version)
        session.flush()
    else:
        version = session.scalar(select(VersionRow).where(VersionRow.dataset_id == identifier))
        if version is None:
            msg = "Quality monitor manifest is missing"
            raise ValidationError(msg)
    return identifier, version.id


def schedule_rule(session: Session, rule_id: str, slot: str) -> DqRun:
    """Enqueue one frozen rule revision once inside an existing write transaction."""
    _lock_targets(session)
    row = session.get(DqRuleRow, rule_id, with_for_update=True)
    rule = get_rule(session, rule_id)
    if row is None or not rule.enabled:
        msg = "Disabled quality rules cannot be scheduled"
        raise ValidationError(msg)
    existing = session.scalar(
        select(DqRunRow).where(
            DqRunRow.rule_id == rule_id,
            DqRunRow.rule_revision == rule.revision,
            DqRunRow.slot == slot,
        )
    )
    if existing is not None:
        return get_run(session, existing.id)
    dataset_id, version_id = _monitor_dataset(session, rule.target.source_id)
    identifier, task_id = new_id(), new_id()
    task = TaskRow(
        id=task_id,
        dataset_id=dataset_id,
        input_version_id=version_id,
        idempotency_key=f"dq:{rule_id}:{rule.revision}:{slot}",
        queue="cpu",
        total_shards=1,
        dq_run_id=identifier,
    )
    session.add(task)
    session.flush()
    session.add(ShardRow(task_id=task_id, ordinal=0, inputs=[]))
    session.add(
        DqRunRow(
            id=identifier,
            rule_id=rule_id,
            rule_revision=rule.revision,
            slot=slot,
            task_id=task_id,
            state="QUEUED",
            rule_payload=rule.model_dump(mode="json"),
        )
    )
    session.flush()
    return get_run(session, identifier)


type _SlotKey = tuple[str, int, str]


def _due_minutes(session: Session, current: datetime) -> dict[_SlotKey, datetime]:
    """Map each enabled rule revision to its newest matching minute in the catch-up window."""
    due: dict[_SlotKey, datetime] = {}
    rows = session.scalars(
        select(DqRuleRow).where(DqRuleRow.deleted.is_(False)).order_by(DqRuleRow.id)
    )
    for row in rows:
        rule = DqRule.model_validate(row.payload)
        if not rule.enabled or not rule.cron:
            continue
        minute = latest_match(rule.cron, current, current - CATCH_UP_WINDOW)
        if minute is not None:
            due[rule.id, rule.revision, minute.isoformat()] = minute
    return due


def _accepted_minutes(
    session: Session, keys: set[tuple[str, int]]
) -> dict[tuple[str, int], datetime]:
    if not keys:
        return {}
    rows = session.scalars(
        select(DqHistoryRow).where(DqHistoryRow.rule_id.in_({rule_id for rule_id, _ in keys}))
    )
    return {
        (row.rule_id, row.revision): DqRuleHistory.model_validate(row.payload)
        .occurred_at.astimezone(UTC)
        .replace(second=0, microsecond=0)
        for row in rows
        if (row.rule_id, row.revision) in keys
    }


def _pending_slots(session: Session, current: datetime) -> tuple[_SlotKey, ...]:
    """Return due slots without a run, excluding catch-up before a revision was accepted."""
    due = _due_minutes(session, current)
    if not due:
        return ()
    rows = session.execute(
        select(DqRunRow.rule_id, DqRunRow.rule_revision, DqRunRow.slot).where(
            DqRunRow.slot.in_({slot for _, _, slot in due})
        )
    )
    existing = {(rule_id, revision, slot) for rule_id, revision, slot in rows}
    missing = {key: minute for key, minute in due.items() if key not in existing}
    accepted = _accepted_minutes(session, {(rule_id, revision) for rule_id, revision, _ in missing})
    return tuple(
        sorted(
            key
            for key, minute in missing.items()
            if minute == current or minute >= accepted.get(key[:2], current)
        )
    )


def schedule_due(db: Database, now: datetime | None = None) -> tuple[DqRun, ...]:
    """Enqueue each rule's newest due UTC minute once; older misses coalesce into it."""
    instant = now or utcnow()
    if instant.tzinfo is None:
        msg = "Quality scheduling requires an aware clock"
        raise ValidationError(msg)
    current = instant.astimezone(UTC).replace(second=0, microsecond=0)
    # Idle ticks only read; scheduling locks are taken when some slot is actually due.
    with db.session() as session:
        pending = _pending_slots(session, current)
    if not pending:
        return ()
    with db.session() as session:
        db.lock_writes(session)
        _lock_targets(session)
        # Lock in ID order: concurrent schedulers share the same uniqueness decision.
        session.scalars(
            select(DqRuleRow)
            .where(DqRuleRow.deleted.is_(False))
            .order_by(DqRuleRow.id)
            .with_for_update()
        ).all()
        still_due = _due_minutes(session, current)
        scheduled = tuple(
            schedule_rule(session, rule_id, slot)
            for rule_id, revision, slot in pending
            if (rule_id, revision, slot) in still_due
        )
        session.commit()
    return scheduled
