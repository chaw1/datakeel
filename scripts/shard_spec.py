# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Parse the ``K/N`` shard selector shared by the pytest and mutation gates."""

from pydantic import Field

from datakeel.core.models import BoundaryModel


class ShardSpec(BoundaryModel):
    """One 1-based shard of a fixed shard count."""

    index: int = Field(ge=1)
    count: int = Field(ge=1)

    def __str__(self) -> str:
        """Render the same ``K/N`` text that selected this shard."""
        return f"{self.index}/{self.count}"


def parse_shard(value: str) -> ShardSpec:
    """Read ``K/N`` and reject malformed values or indexes outside ``1..N``."""
    index, separator, count = value.partition("/")
    if not separator or not index.isdigit() or not count.isdigit():
        msg = f"shard must look like K/N, got {value!r}"
        raise ValueError(msg)
    if not 1 <= int(index) <= int(count):
        msg = f"shard index must be between 1 and N, got {value!r}"
        raise ValueError(msg)
    return ShardSpec(index=int(index), count=int(count))
