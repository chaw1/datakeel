# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Bound independent mutation subprocesses while preserving catalog result order."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Iterator


def ordered_parallel_map[Item, Result](
    operation: Callable[[Item], Result], inputs: Iterable[Item], *, workers: int
) -> Iterator[Result]:
    """Return every outcome in input order, propagating worker errors without treating kills."""
    if workers == 1:
        yield from map(operation, inputs)
        return
    with ThreadPoolExecutor(max_workers=workers) as executor:
        yield from executor.map(operation, inputs)
