# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""A dbt rerun of unchanged code is a new run record, not a catalog change."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from datakeel.catalog.metadata_service import import_dbt
from datakeel.core.metadata_imports import DbtImportRequest
from datakeel.core.models import JsonDocument
from datakeel.storage.events import all_events

if TYPE_CHECKING:
    from datakeel.storage.database import Database

_FIXTURES = Path(__file__).parents[1] / "fixtures" / "dbt"
_TEST = "test.p22_shop.unique_orders_order_id.fed79b3a6e"


def _results() -> dict[str, Any]:
    return json.loads((_FIXTURES / "run_results.json").read_text())


def _rerun(results: dict[str, Any], invocation: str) -> dict[str, Any]:
    """Rewrite what a second `dbt build` of the same code on the same data changes."""
    rerun = json.loads(json.dumps(results))
    rerun["metadata"].update(invocation_id=invocation, generated_at="2026-10-28T03:00:00Z")
    rerun["elapsed_time"] = 9.5
    for index, entry in enumerate(rerun["results"]):
        entry["execution_time"] = 1.25 + index
        entry["thread_id"] = f"Thread-{index + 7} (worker)"
        entry["timing"] = [
            {
                "name": "execute",
                "started_at": "2026-10-28T02:59:58Z",
                "completed_at": "2026-10-28T02:59:59Z",
            }
        ]
        entry["adapter_response"] = {**entry["adapter_response"], "query_id": f"q-{index}"}
    return rerun


def _request(results: dict[str, Any]) -> DbtImportRequest:
    return DbtImportRequest(
        source_id="shop",
        manifest=JsonDocument.model_validate_json((_FIXTURES / "manifest.json").read_text()),
        catalog=JsonDocument.model_validate_json((_FIXTURES / "catalog.json").read_text()),
        run_results=JsonDocument(results),
    )


def _run_records(db: Database) -> dict[str, dict[str, Any]]:
    with db.session() as session:
        runs = [event.params.get("dbt_run") for event in all_events(session)]
    return {run["invocation_id"]: run for run in runs if run}


def test_dbt_rerun_without_changes_reports_everything_unchanged_and_keeps_run_record(
    db: Database,
) -> None:
    """Timings, threads, adapter receipts and invocation identity never mark objects changed."""
    first = import_dbt(db, _request(_results()))
    rerun = import_dbt(db, _request(_rerun(_results(), "second-invocation")))
    assert (rerun.new, rerun.changed, rerun.deleted) == (0, 0, 0)
    assert rerun.unchanged == first.object_count
    assert rerun.event_id is None
    records = _run_records(db)
    assert sorted(records) == ["d7646616-75ff-459c-aa50-fe687e2f7b05", "second-invocation"]
    latest = {entry["unique_id"]: entry for entry in records["second-invocation"]["results"]}
    assert latest[_TEST]["execution_time"] == 7.25
    assert latest[_TEST]["adapter_response"]["query_id"] == "q-6"
    assert "compiled_code" not in latest[_TEST]
    import_dbt(db, _request(_rerun(_results(), "second-invocation")))
    assert len(_run_records(db)) == 2


def test_dbt_rerun_with_changed_test_outcome_is_a_catalog_change(db: Database) -> None:
    """Status and failure counts are quality evidence: a failing test still changes objects."""
    import_dbt(db, _request(_results()))
    failing = _rerun(_results(), "failing-invocation")
    entry = next(item for item in failing["results"] if item["unique_id"] == _TEST)
    entry.update(status="fail", failures=2, message="Got 2 results, configured to fail if != 0")
    report = import_dbt(db, _request(failing))
    assert report.changed == 2  # the orders table and its order_id column carry the test
    assert report.event_id is not None
