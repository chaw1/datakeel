# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Refresh a worker attempt without reviving lost ownership."""

import threading

from datakeel.worker.queue import DatabaseQueue, Lease


def pulse(queue: DatabaseQueue, lease: Lease, stop: threading.Event) -> None:
    """Stop refreshing as soon as another attempt owns the shard."""
    while not stop.wait(max(0.1, queue.lease_seconds / 3)):
        if not queue.heartbeat(lease):
            return
