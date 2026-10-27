# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Schedule quality checks through the existing task shards and lease reaper."""

from datetime import UTC, datetime
from hashlib import sha256

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from datakeel.core.dq_cron import cron_matches
from datakeel.core.dq_models import DqRule
from datakeel.core.dq_monitor import DqRun
from datakeel.core.errors import ValidationError
from datakeel.core.models import new_id, utcnow
from datakeel.storage.database import Database, DatasetRow, ShardRow, TaskRow, VersionRow
from datakeel.storage.dq_reads import get_run
from datakeel.storage.dq_rows import DqRuleRow, DqRunRow
from datakeel.storage.dq_store import get_rule


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


def schedule_due(db: Database, now: datetime | None = None) -> tuple[DqRun, ...]:
    """Enqueue current UTC minute matches; missed minutes are deliberately skipped."""
    instant = now or utcnow()
    if instant.tzinfo is None:
        msg = "Quality scheduling requires an aware clock"
        raise ValidationError(msg)
    now = instant.astimezone(UTC)
    slot = now.replace(second=0, microsecond=0).isoformat()
    scheduled: list[DqRun] = []
    with db.session() as session:
        db.lock_writes(session)
        _lock_targets(session)
        # Lock in ID order: concurrent schedulers share the same uniqueness decision.
        rules = session.scalars(
            select(DqRuleRow)
            .where(DqRuleRow.deleted.is_(False))
            .order_by(DqRuleRow.id)
            .with_for_update()
        )
        for row in rules:
            rule = DqRule.model_validate(row.payload)
            if rule.enabled and rule.cron and cron_matches(rule.cron, now):
                scheduled.append(schedule_rule(session, rule.id, slot))
        session.commit()
    return tuple(scheduled)
