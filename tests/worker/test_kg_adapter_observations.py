# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Expose recovered provider output diagnostics through fresh and cached worker results."""

from __future__ import annotations

from typing import TYPE_CHECKING

from tests.kg.integration_helpers import (
    execute_graph,
    install_adapter,
    pair_result,
    prepare_graph,
    text_dataset,
)

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

    from datakeel.storage.database import Database


def test_worker_when_schema_echo_recovered_reports_ignored_keys_across_cache_reuse(
    db: Database,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Recovered extraneous keys remain counted when the successful block is replayed."""
    dataset = text_dataset(db, tmp_path, ("Acme uses Widget.",))
    adapter = install_adapter(
        monkeypatch, (pair_result().model_copy(update={"ignored_top_level_keys": 5}),)
    )
    first = execute_graph(db, prepare_graph(db, dataset))
    cached = execute_graph(db, prepare_graph(db, dataset))
    assert first.report.ignored_top_level_keys == 5
    assert cached.report.ignored_top_level_keys == 5
    assert cached.report.cached == 1
    assert adapter.calls == 1
