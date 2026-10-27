# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Sign and relay generic quality alerts using explicitly configured transports."""

import hashlib
import hmac
from collections.abc import Callable
from datetime import datetime
from http import HTTPStatus

import httpx

from datakeel.core.models import utcnow
from datakeel.core.settings import Settings
from datakeel.storage.database import Database
from datakeel.storage.dq_webhooks import claim_delivery, finish_delivery


def webhook_signature(secret: str, timestamp: str, body: str) -> str:
    """Bind the exact UTF-8 body and timestamp with an HMAC-SHA256 digest."""
    digest = hmac.new(secret.encode(), f"{timestamp}.{body}".encode(), hashlib.sha256).hexdigest()
    return "sha256=" + digest


def relay_webhooks(
    db: Database,
    settings: Settings,
    *,
    now: datetime | None = None,
    transport: httpx.BaseTransport | None = None,
    clock: Callable[[], datetime] = utcnow,
) -> int:
    """Attempt one durable alert, retaining failures for later worker ticks."""
    if not settings.dq_webhook_url or settings.dq_webhook_secret is None:
        return 0
    now = now or clock()
    delivery = claim_delivery(db, now, settings.dq_webhook_max_attempts)
    if delivery is None:
        return 0
    timestamp = str(int(now.timestamp()))
    headers = {
        "Content-Type": "application/json",
        "X-Datakeel-Event-Id": delivery.id,
        "X-Datakeel-Timestamp": timestamp,
        "X-Datakeel-Signature": webhook_signature(
            settings.dq_webhook_secret.get_secret_value(),
            timestamp,
            delivery.body,
        ),
    }
    try:
        with httpx.Client(
            timeout=5, trust_env=False, follow_redirects=False, transport=transport
        ) as client:
            response = client.post(settings.dq_webhook_url, content=delivery.body, headers=headers)
        delivered = HTTPStatus.OK <= response.status_code < HTTPStatus.MULTIPLE_CHOICES
    except httpx.HTTPError:
        delivered = False
    finish_delivery(
        db, delivery, now, delivered=delivered, retry_seconds=settings.dq_webhook_retry_seconds
    )
    return int(delivered)
