# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

# Typed native implementation; import the public package interface.

from collections.abc import Sequence
from typing import Literal

__version__: str

def compare(
    hashes: Sequence[int],
    threshold: int = 8,
    prefix_bits: int = 4,
    mode: Literal["prefix", "exact"] = "prefix",
) -> list[tuple[int, int, int]]: ...
