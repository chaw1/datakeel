# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Persistent recovery-home isolation shared by startup and background execution."""

from pathlib import Path

from datakeel.core.errors import ValidationError
from datakeel.core.settings import get_settings

ISOLATION_MARKER = "recovery-isolation.json"


def require_unisolated(home: Path, database: Path | None = None) -> None:
    """Refuse service activation in a restored home, even with a different settings home."""
    roots = (home.resolve(),) if database is None else (home.resolve(), database.resolve().parent)
    if any(
        (root / ISOLATION_MARKER).exists() or (root / ISOLATION_MARKER).is_symlink()
        for root in roots
    ):
        msg = "Recovery isolation: services and outbound execution are disabled"
        raise ValidationError(msg)


def require_active_home(database_name: str | None = None) -> None:
    """Block scheduling and relays even if called outside the worker's admission path."""
    require_unisolated(get_settings().home, Path(database_name) if database_name else None)
