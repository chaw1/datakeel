# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Durable leased webhook delivery with fenced completion and bounded backoff."""

from datetime import datetime

from sqlalchemy import or_, select

from datakeel.core.dq_monitor import DqWebhookDelivery
from datakeel.core.models import new_id
from datakeel.storage.database import Database
from datakeel.storage.dq_rows import DqWebhookRow


def claim_delivery(db: Database, now: datetime, max_attempts: int = 8) -> DqWebhookDelivery | None:
    """Claim one due alert or reclaim a delivery abandoned by a dead worker."""
    timestamp = now.timestamp()
    with db.session() as session:
        db.lock_writes(session)
        row = session.scalar(
            select(DqWebhookRow)
            .where(
                DqWebhookRow.delivered.is_(False),
                DqWebhookRow.due_at <= timestamp,
                DqWebhookRow.attempts < max_attempts,
                or_(DqWebhookRow.lease_owner.is_(None), DqWebhookRow.leased_until <= timestamp),
            )
            .order_by(DqWebhookRow.due_at, DqWebhookRow.id)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        if row is None:
            return None
        owner = new_id()
        row.lease_owner, row.leased_until = owner, timestamp + 30
        row.attempts += 1
        delivery = DqWebhookDelivery(id=row.id, owner=owner, body=row.body, attempts=row.attempts)
        session.commit()
        return delivery


def finish_delivery(
    db: Database,
    delivery: DqWebhookDelivery,
    now: datetime,
    *,
    delivered: bool,
    retry_seconds: float = 5,
) -> bool:
    """Acknowledge the owned attempt or persist its exponentially delayed retry."""
    with db.session() as session:
        db.lock_writes(session)
        row = session.get(DqWebhookRow, delivery.id, with_for_update=True)
        if row is None or row.lease_owner != delivery.owner:
            return False
        row.delivered, row.lease_owner, row.leased_until = delivered, None, None
        row.due_at = now.timestamp() + min(retry_seconds * 2 ** (delivery.attempts - 1), 3600)
        session.commit()
        return True
