# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Immutable task query responses shared by HTTP and worker callers."""

from pydantic import Field

from datakeel.core.media_models import MediaFailure
from datakeel.core.models import Record


class ShardView(Record):
    """Public progress for one shard, excluding internal lease tokens."""

    id: str
    state: str
    attempts: int
    ordinal: int


class TaskView(Record):
    """Persisted task state and derived completion progress.

    ``failed_files`` lists recordings published with a processing failure, and
    ``partial`` marks a completed task whose output includes such failures.
    """

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
    failed_files: list[MediaFailure] = Field(default_factory=list[MediaFailure])
    partial: bool = False
