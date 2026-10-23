# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Rebuild disposable catalog projections from their immutable metadata events."""

from rich.console import Console

from datakeel.storage.catalog_projection import rebuild_catalog
from datakeel.storage.database import Database


def rebuild(db: Database, expected_hash: str | None = None) -> None:
    """Replay metadata and return a failing exit status for a canonical hash mismatch."""
    result = rebuild_catalog(db, expected_hash)
    Console().print(result.model_dump_json(indent=2), markup=False, highlight=False, soft_wrap=True)
    if not result.matches:
        raise SystemExit(1)
