# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""The smallest capacity workloads still exercise actual operators and process failure."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import text

from scripts.scale_bench import pipeline, worker
from scripts.scale_bench.models import SCALES, Config, Context

if TYPE_CHECKING:
    from pathlib import Path

    from datakeel.storage.database import Database


def _context(db: Database, root: Path, *, recovery: bool) -> Context:
    root.mkdir()
    schema = None
    if not db.sqlite:
        with db.engine.connect() as connection:
            schema = str(connection.scalar(text("SELECT current_schema()")))
    return Context(
        config=Config(scenario="B6" if recovery else "B2", workers=1),
        scale=SCALES["S"].model_copy(update={"files": 4, "tasks": 2}),
        db=db,
        root=root,
        schema_name=schema,
    )


def test_pipeline_workload_scores_real_published_operator_outputs(
    db: Database, tmp_path: Path
) -> None:
    """Even tiny runs create real files, leased work, quality evidence and output versions."""
    result = pipeline.run(_context(db, tmp_path / "pipeline", recovery=False))
    assert result.counts["files"] == 4
    assert result.metrics["quality_total"] == 100
    assert result.metrics["retry_attempts"] == 0
    assert result.fixture_sha256


def test_recovery_workload_distinguishes_retry_from_duplicate_publication(
    db: Database, tmp_path: Path
) -> None:
    """A killed real operator attempt is retried and still commits one version per task."""
    result = worker.run(_context(db, tmp_path / "recovery", recovery=True))
    assert result.counts["tasks"] == 2
    assert result.counts["retry_attempts"] == 1
    assert result.counts["lost_tasks"] == 0
    assert result.counts["duplicate_publications"] == 0
    assert result.counts["terminal_events"] == 2
    assert result.counts["pipeline_events"] == 4
    assert result.counts["output_files"] == 2
    assert result.metrics["killed_workers"] == 1
    assert result.metrics["killed_exit_code"] == -9
    assert result.metrics["executed_attempts"] == 3
