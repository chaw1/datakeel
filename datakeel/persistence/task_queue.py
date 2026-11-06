# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Application queue composition; completion handlers share its writer transaction."""

from datakeel.persistence.task_completion import BoundTaskCompletion
from datakeel.storage.custom_validation import validate_custom_pipeline
from datakeel.storage.database import Database
from datakeel.worker_store.task_queue import DatabaseQueue as QueueStore


class DatabaseQueue(QueueStore):
    """Construct the queue with explicit, transaction-bound legacy domain adapters."""

    def __init__(self, db: Database, lease_seconds: float = 30, max_attempts: int = 3) -> None:
        """Keep the existing application constructor and retry policy."""
        super().__init__(
            db,
            lease_seconds,
            max_attempts,
            completion_factory=BoundTaskCompletion,
            validate_registered=validate_custom_pipeline,
        )
