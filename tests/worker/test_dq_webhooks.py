# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Verify signed alert retries only against a local generated HTTP receiver."""

from __future__ import annotations

import hashlib
import hmac
import threading
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import TYPE_CHECKING

import httpx
from pydantic import SecretStr

from datakeel.core.settings import Settings
from datakeel.storage.dq_rows import DqWebhookRow
from datakeel.storage.dq_webhooks import claim_delivery, finish_delivery
from datakeel.worker.dq_webhooks import relay_webhooks, webhook_signature

if TYPE_CHECKING:
    from collections.abc import Iterator

    from datakeel.storage.database import Database

import pytest


@pytest.fixture
def receiver() -> Iterator[tuple[str, list[tuple[bytes, str, str]]]]:
    """Run an ephemeral loopback receiver which fails once and then accepts."""
    received: list[tuple[bytes, str, str]] = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # stdlib HTTP handler callback name.
            body = self.rfile.read(int(self.headers["Content-Length"]))
            received.append(
                (body, self.headers["X-Datakeel-Timestamp"], self.headers["X-Datakeel-Signature"])
            )
            self.send_response(503 if len(received) == 1 else 204)
            self.end_headers()

        def log_message(self, format: str, *args: object) -> None:  # noqa: A002  # stdlib callback.
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}/alerts", received
    server.shutdown()
    server.server_close()
    thread.join()


def _seed(db: Database, now: datetime) -> None:
    with db.session() as session:
        session.add(
            DqWebhookRow(
                id="event-one",
                body='{"event":"generated"}',
                due_at=now.timestamp(),
                delivered=False,
                attempts=0,
            )
        )
        session.commit()


def test_local_receiver_verifies_signature_and_retry_backoff(
    db: Database,
    receiver: tuple[str, list[tuple[bytes, str, str]]],
) -> None:
    """A 503 persists a retry, and the injected clock controls its next delivery."""
    url, received = receiver
    now = datetime(2026, 1, 1, tzinfo=UTC)
    settings = Settings(dq_webhook_url=url, dq_webhook_secret=SecretStr("generated-test-secret"))
    _seed(db, now)
    assert relay_webhooks(db, settings, now=now) == 0
    assert len(received) == 1
    body, timestamp, signature = received[0]
    expected = hmac.new(
        b"generated-test-secret", timestamp.encode() + b"." + body, hashlib.sha256
    ).hexdigest()
    assert hmac.compare_digest(signature, "sha256=" + expected)
    assert relay_webhooks(db, settings, now=now + timedelta(seconds=4)) == 0
    assert len(received) == 1
    assert relay_webhooks(db, settings, now=now + timedelta(seconds=5)) == 1
    assert len(received) == 2
    assert relay_webhooks(db, settings, now=now + timedelta(seconds=100)) == 0


def test_delivery_lease_reclaim_fences_old_ack_and_max_attempts(db: Database) -> None:
    """A crashed sender cannot acknowledge a reclaimed lease or retry forever."""
    now = datetime(2026, 1, 1, tzinfo=UTC)
    _seed(db, now)
    initial = claim_delivery(db, now, 2)
    assert initial is not None
    assert claim_delivery(db, now, 2) is None
    fresh = claim_delivery(db, now + timedelta(seconds=31), 2)
    assert fresh is not None
    assert fresh.owner != initial.owner
    assert not finish_delivery(db, initial, now, delivered=True)
    assert finish_delivery(db, fresh, now, delivered=False, retry_seconds=5)
    assert claim_delivery(db, now + timedelta(seconds=11), 2) is None


def test_network_failure_persists_retry_and_unconfigured_relay_is_inert(db: Database) -> None:
    """Connection errors stay in the durable outbox and no default endpoint exists."""
    now = datetime(2026, 1, 1, tzinfo=UTC)
    _seed(db, now)
    assert relay_webhooks(db, Settings(), now=now) == 0

    def disconnected(request: httpx.Request) -> httpx.Response:
        msg = "Generated connection failure"
        raise httpx.ConnectError(msg, request=request)

    settings = Settings(
        dq_webhook_url="http://receiver.invalid/alerts",
        dq_webhook_secret=SecretStr("generated-test-secret"),
    )
    assert (
        relay_webhooks(db, settings, clock=lambda: now, transport=httpx.MockTransport(disconnected))
        == 0
    )
    assert claim_delivery(db, now + timedelta(seconds=4)) is None
    assert claim_delivery(db, now + timedelta(seconds=5)) is not None
    assert webhook_signature("secret", "1", "body") != webhook_signature("secret", "2", "body")
