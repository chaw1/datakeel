# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Process-released maintenance exclusion for a whole SQLite upgrade campaign."""

import fcntl
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from datakeel.core.recovery import require_unisolated

__all__ = ["maintenance_lock", "require_unisolated"]


@contextmanager
def maintenance_lock(path: Path) -> Generator[None]:
    """Hold one inode lock across backup and every version commit; never unlink it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.with_name(path.name + ".maintenance.lock").open("a+b") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)
