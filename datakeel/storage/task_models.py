# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Immutable task query responses shared by HTTP and worker callers."""

from datakeel.core.models import Record


class ShardView(Record):
    """Public progress for one shard, excluding internal lease tokens."""

    id: str
    state: str
    attempts: int
    ordinal: int


class TaskView(Record):
    """Persisted task state and derived completion progress."""

    id: str
    dataset_id: str
    input_version_id: str | None
    state: str
    progress: float
    total_shards: int
    completed_shards: int
    error: str | None
    created_at: float
    finished_at: float | None
    shards: list[ShardView]
