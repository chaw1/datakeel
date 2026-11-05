# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Worker-owned schema without task completion or queue behavior."""

from datakeel.core.schema import SchemaContribution
from datakeel.worker_store.rows import OutboxRow, ShardRow, TaskRow

SCHEMA = SchemaContribution(
    owner="worker_store",
    order=0,
    rows=(TaskRow, ShardRow, OutboxRow),
)
