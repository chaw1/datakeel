# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""RUNNING, ABORT and OTHER follow the standard run lifecycle beside START/COMPLETE/FAIL."""

from pathlib import Path

import pytest

from datakeel.core.metadata_imports import ExternalMetadata
from datakeel.core.models import JsonDocument
from datakeel.core.orchestration import OpenLineageRunEvent
from datakeel.lineage.service import graph
from datakeel.storage.catalog_store import read_snapshot
from datakeel.storage.database import Database
from datakeel.storage.events import all_events
from datakeel.storage.openlineage_store import ingest_openlineage

FIXTURE = Path(__file__).parents[1] / "fixtures" / "metadata" / "openlineage.json"


def observation(event_type: str, event_time: str, run_id: str = "run-one") -> OpenLineageRunEvent:
    """Vary one generated producer event by transition, time and run identity."""
    raw = JsonDocument.model_validate_json(FIXTURE.read_text()).root
    return OpenLineageRunEvent.model_validate(
        {**raw, "eventType": event_type, "eventTime": event_time, "run": {"runId": run_id}}
    )


def _job(db: Database, job_id: str) -> ExternalMetadata:
    with db.session() as session:
        item = next(
            obj for obj in read_snapshot(session).objects if obj.asset_ref.asset_id == job_id
        )
    return ExternalMetadata.model_validate(item.properties["integration"])


def test_openlineage_running_keeps_run_in_progress_until_terminal(db: Database) -> None:
    """RUNNING after START stays in progress; COMPLETE then wins regardless of later RUNNING."""
    ingest_openlineage(db, observation("START", "2026-10-27T01:00:00Z"))
    running = ingest_openlineage(db, observation("RUNNING", "2026-10-27T01:02:00Z"))
    assert running.state == "RUNNING"
    ingest_openlineage(db, observation("COMPLETE", "2026-10-27T01:05:00Z"))
    late = ingest_openlineage(db, observation("RUNNING", "2026-10-27T01:09:00Z"))
    assert late.inserted is False
    assert late.state == "COMPLETE"
    assert _job(db, late.job_id).details["last_success"] == "2026-10-27T01:05:00+00:00"


def test_openlineage_abort_is_terminal_without_success_or_graph_edges(db: Database) -> None:
    """An aborted run is not fresh output and draws no completed lineage edge."""
    ingest_openlineage(db, observation("START", "2026-10-27T01:00:00Z"))
    aborted = ingest_openlineage(db, observation("ABORT", "2026-10-27T01:03:00Z"))
    late_start = ingest_openlineage(db, observation("START", "2026-10-27T01:04:00Z", "run-two"))
    assert aborted.state == "ABORT"
    job = _job(db, aborted.job_id)
    assert job.details["last_success"] is None
    assert [run["state"] for run in job.details["runs"]] == ["START", "ABORT"]
    assert late_start.state == "START"
    with db.session() as session:
        states = {
            event.run_state for event in all_events(session) if event.operator == "OPENLINEAGE_RUN"
        }
    assert states == {"RUNNING", "ABORT"}


@pytest.mark.parametrize("first", ["START", "FAIL"])
def test_openlineage_other_never_changes_observed_state(db: Database, first: str) -> None:
    """OTHER carries metadata only and cannot override START or a terminal state."""
    ingest_openlineage(db, observation(first, "2026-10-27T01:00:00Z"))
    other = ingest_openlineage(db, observation("OTHER", "2026-10-27T02:00:00Z"))
    assert other.inserted is True
    assert other.state == first


def test_openlineage_other_alone_reports_observation_state(db: Database) -> None:
    """A run known only from OTHER is visible but not reported as started or successful."""
    other = ingest_openlineage(db, observation("OTHER", "2026-10-27T02:00:00Z"))
    assert other.state == "OTHER"
    assert _job(db, other.job_id).details["last_success"] is None


def test_openlineage_abort_graph_keeps_assets_without_edges(db: Database) -> None:
    """Graph projection lists an aborted run's datasets but connects none of them."""
    receipt = ingest_openlineage(db, observation("ABORT", "2026-10-27T01:03:00Z"))
    with db.session() as session:
        aborted = graph(all_events(session))
    ingest_openlineage(db, observation("COMPLETE", "2026-10-27T01:09:00Z", "run-two"))
    with db.session() as session:
        completed = graph(all_events(session))
    assert receipt.inserted is True
    assert aborted.nodes
    assert not aborted.edges
    assert completed.edges
