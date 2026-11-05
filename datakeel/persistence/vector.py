# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Explicit fake-vector schema owner, separate from legacy domain registration."""

from datakeel.core.schema import SchemaContribution
from datakeel.storage.vector_rows import VectorAccountRow, VectorAttemptRow, VectorCacheRow

SCHEMA = SchemaContribution(
    owner="vector_store",
    order=25,
    rows=(VectorAccountRow, VectorAttemptRow, VectorCacheRow),
)
